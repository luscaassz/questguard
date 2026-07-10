from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import sys
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.analysis.diversity_metrics import compute_set_metrics, structural_signature
from questguard.bootstrap import build_application
from questguard.domain.issues import combine_reports
from questguard.generation.baseline_service import BaselineGenerationService
from questguard.repair.diversity_aware import (
    DiversityAwareQuestRepairer,
    DiversityRepairState,
)
from questguard.repair.orchestrator import RepairOrchestrator
from questguard.reports.io import save_json, save_text
from questguard.validation.base import QuestValidator


def validate_quests(
    quests: List[Dict[str, Any]],
    validators: Sequence[QuestValidator],
):
    records = []
    accepted = []
    rejected = []

    for quest in quests:
        reports = [validator.validate(quest) for validator in validators]
        combined = combine_reports(reports)
        record = {
            "quest_id": quest.get("quest_id"),
            "passed": combined.passed,
            "error_count": combined.error_count,
            "warning_count": combined.warning_count,
            "reports": [report.to_dict() for report in reports],
        }
        records.append(record)
        (accepted if combined.passed else rejected).append(quest)

    return records, accepted, rejected


def summarize(quests, records, accepted, rejected, world):
    total = len(quests)
    return {
        "total_generated": total,
        "valid_count": len(accepted),
        "invalid_count": len(rejected),
        "validity_rate": len(accepted) / total if total else 0.0,
        "average_errors_per_quest": (
            sum(record["error_count"] for record in records) / total
            if total
            else 0.0
        ),
        "average_warnings_per_quest": (
            sum(record["warning_count"] for record in records) / total
            if total
            else 0.0
        ),
        "set_metrics_all_generated": compute_set_metrics(quests, world),
        "set_metrics_valid_outputs": compute_set_metrics(accepted, world),
        "records": records,
    }


def generate(
    service,
    batches: int,
    quests_per_batch: int,
    *,
    configuration_name: str,
    raw_output_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    quests: List[Dict[str, Any]] = []
    diagnostics: List[Dict[str, Any]] = []

    for batch_index in range(1, batches + 1):
        print(
            f"[{configuration_name}] Gerando batch "
            f"{batch_index}/{batches} com {quests_per_batch} quests..."
        )

        batch = service.generate_batch(
            batch_index=batch_index,
            number_of_quests=quests_per_batch,
            forbidden_signatures=(),
        )

        quests.extend(batch.quests)

        raw_path = (
            raw_output_dir
            / configuration_name
            / f"batch_{batch_index:02d}.txt"
        )
        save_text(batch.raw_response, raw_path)

        diagnostics.append(
            {
                "batch_index": batch_index,
                "requested_count": batch.requested_count or quests_per_batch,
                "returned_count": len(batch.quests),
                "generation_call_count": batch.generation_call_count,
                "shortfall": batch.shortfall,
                "raw_response_path": str(raw_path),
            }
        )

        print(
            f"[{configuration_name}] Batch {batch_index:02d}: "
            f"{len(batch.quests)} quests em "
            f"{batch.generation_call_count} chamada(s)."
        )

    return quests, diagnostics


def finalize_repair_summary(
    *,
    original_quests: List[Dict[str, Any]],
    initial_valid: List[Dict[str, Any]],
    final_candidates: List[Dict[str, Any]],
    repair_records: List[Dict[str, Any]],
    validators: Sequence[QuestValidator],
    world,
    generation_diagnostics: List[Dict[str, Any]],
    total_generation_calls: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    final_records, final_valid, final_rejected = validate_quests(
        final_candidates,
        validators,
    )
    summary = summarize(
        final_candidates,
        final_records,
        final_valid,
        final_rejected,
        world,
    )

    original_total = len(original_quests)
    repair_successes = sum(
        int(record["passed_after_repair"])
        for record in repair_records
    )
    final_yield = len(final_valid) / original_total if original_total else 0.0

    summary.update(
        {
            "original_generated_count": original_total,
            "initial_validity_rate": (
                len(initial_valid) / original_total
                if original_total
                else 0.0
            ),
            "final_valid_output_count": len(final_valid),
            "final_yield_over_original_generation": final_yield,
            "validity_rate": final_yield,
            "repair_attempted_quests": len(repair_records),
            "repair_successes": repair_successes,
            "repair_failures": len(repair_records) - repair_successes,
            "repair_success_rate": (
                repair_successes / len(repair_records)
                if repair_records
                else 0.0
            ),
            "deterministic_only_repairs": sum(
                int(
                    record["passed_after_repair"]
                    and record["llm_attempts"] == 0
                )
                for record in repair_records
            ),
            "total_llm_repair_calls": sum(
                record["llm_attempts"]
                for record in repair_records
            ),
            "repair_records": repair_records,
            "generation_diagnostics": generation_diagnostics,
            "total_generation_calls": total_generation_calls,
        }
    )
    return summary, final_valid


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara C1-C5 para o experimento do artigo."
    )
    parser.add_argument("--batches", type=int, default=3)
    parser.add_argument("--quests-per-batch", type=int, default=10)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()

    if args.batches <= 0:
        raise ValueError("--batches deve ser maior que zero.")
    if args.quests_per_batch <= 0:
        raise ValueError("--quests-per-batch deve ser maior que zero.")

    # Uma seed diferente é criada automaticamente para cada execução
    # completa do experimento.
    run_seed = secrets.randbelow(2_147_483_646) + 1

    print("=" * 70)
    print(f"Seed automática desta execução: {run_seed}")
    print("=" * 70)

    app = build_application(args.project_root)

    seed_setter = getattr(app.llm, "set_seed", None)

    if not callable(seed_setter):
        raise TypeError(
            "O cliente LLM não oferece o método set_seed(). "
            "Verifique se o OllamaClient atualizado está sendo usado."
        )

    seed_setter(run_seed)
    baseline = BaselineGenerationService(
        llm=app.llm,
        settings=app.settings,
        world=app.world,
    )
    validators = app.deterministic_validators
    results: Dict[str, Any] = {}

    experiment_dir = app.settings.output_dir / "configuration_experiment"
    raw_output_dir = experiment_dir / "raw_responses"

    experiment_metadata = {
        "run_seed": run_seed,
        "seed_strategy": "run_seed_plus_request_index",
        "generation_model": app.settings.generation_model,
        "review_model": app.settings.review_model,
        "generation_temperature": (
            app.settings.generation_temperature
        ),
        "review_temperature": (
            app.settings.review_temperature
        ),
        "top_p": app.settings.top_p,
        "batches": args.batches,
        "quests_per_batch": args.quests_per_batch,
        "total_quests_per_configuration": (
            args.batches * args.quests_per_batch
        ),
    }

    # C1: prompt simples, sem schema e sem gates durante a geração.
    c1_quests, c1_generation = generate(
        baseline,
        args.batches,
        args.quests_per_batch,
        configuration_name="C1_prompt_only",
        raw_output_dir=raw_output_dir,
    )
    c1_records, c1_valid, c1_invalid = validate_quests(c1_quests, validators)
    c1_summary = summarize(
        c1_quests,
        c1_records,
        c1_valid,
        c1_invalid,
        app.world,
    )
    c1_summary["generation_diagnostics"] = c1_generation
    c1_summary["total_generation_calls"] = sum(
        item["generation_call_count"] for item in c1_generation
    )
    results["C1_prompt_only"] = c1_summary
    save_json(c1_quests, experiment_dir / "C1_prompt_only_quests.json")

    # C2: schema e regras apenas no prompt; validação feita ex post.
    c2_quests, c2_generation = generate(
        app.generation_service,
        args.batches,
        args.quests_per_batch,
        configuration_name="C2_schema_guided",
        raw_output_dir=raw_output_dir,
    )
    c2_records, c2_valid, c2_invalid = validate_quests(c2_quests, validators)
    c2_summary = summarize(
        c2_quests,
        c2_records,
        c2_valid,
        c2_invalid,
        app.world,
    )
    c2_summary["generation_diagnostics"] = c2_generation
    c2_summary["total_generation_calls"] = sum(
        item["generation_call_count"] for item in c2_generation
    )
    results["C2_schema_guided"] = c2_summary
    save_json(c2_quests, experiment_dir / "C2_schema_guided_quests.json")

    # C3: mesma geração de C2, mas somente artefatos aprovados são publicados.
    c3_summary = summarize(
        c2_quests,
        c2_records,
        c2_valid,
        c2_invalid,
        app.world,
    )
    c3_summary["published_output_count"] = len(c2_valid)
    c3_summary["rejected_by_quality_gate"] = len(c2_invalid)
    c3_summary["generation_diagnostics"] = c2_generation
    c3_summary["total_generation_calls"] = c2_summary["total_generation_calls"]
    results["C3_quality_gates"] = c3_summary
    save_json(c2_valid, experiment_dir / "C3_published_quests.json")

    # C4: reparo orientado apenas à validade.
    c4_candidates = list(c2_valid)
    c4_repair_records: List[Dict[str, Any]] = []

    for quest in c2_invalid:
        before_signature = structural_signature(quest, app.world)
        repair_result = app.repair_orchestrator.repair(quest)
        passed = combine_reports(repair_result.reports).passed
        after_signature = structural_signature(repair_result.final_quest, app.world)

        if passed:
            c4_candidates.append(repair_result.final_quest)

        c4_repair_records.append(
            {
                "quest_id": quest.get("quest_id"),
                "llm_attempts": repair_result.attempts,
                "repaired": repair_result.repaired,
                "passed_after_repair": passed,
                "before_signature": before_signature,
                "after_signature": after_signature,
                "deterministic_changes": repair_result.deterministic_changes,
                "reports": [
                    report.to_dict()
                    for report in repair_result.reports
                ],
            }
        )

    c4_summary, c4_valid = finalize_repair_summary(
        original_quests=c2_quests,
        initial_valid=c2_valid,
        final_candidates=c4_candidates,
        repair_records=c4_repair_records,
        validators=validators,
        world=app.world,
        generation_diagnostics=c2_generation,
        total_generation_calls=c2_summary["total_generation_calls"],
    )
    results["C4_quality_gates_repair"] = c4_summary
    save_json(c4_valid, experiment_dir / "C4_final_quests.json")
    save_json(c4_repair_records, experiment_dir / "C4_repair_records.json")

    # C5: reparo consciente de diversidade sobre as mesmas quests rejeitadas.
    diversity_state = DiversityRepairState.from_quests(c2_valid, app.world)
    diversity_repairer = DiversityAwareQuestRepairer(
        world=app.world,
        schema=app.schema,
        state=diversity_state,
    )
    c5_orchestrator = RepairOrchestrator(
        llm=app.llm,
        settings=app.settings,
        world=app.world,
        schema=app.schema,
        validators=validators,
        deterministic_repairer=diversity_repairer,
    )

    c5_candidates = list(c2_valid)
    c5_repair_records: List[Dict[str, Any]] = []

    for quest in c2_invalid:
        state_before = diversity_state.to_dict()
        before_signature = structural_signature(quest, app.world)
        repair_result = c5_orchestrator.repair(quest)
        passed = combine_reports(repair_result.reports).passed
        after_signature = structural_signature(repair_result.final_quest, app.world)

        if passed:
            c5_candidates.append(repair_result.final_quest)
            diversity_state.register(repair_result.final_quest, app.world)

        c5_repair_records.append(
            {
                "quest_id": quest.get("quest_id"),
                "llm_attempts": repair_result.attempts,
                "repaired": repair_result.repaired,
                "passed_after_repair": passed,
                "before_signature": before_signature,
                "after_signature": after_signature,
                "signature_was_already_used": (
                    state_before["signature_counts"].get(after_signature, 0) > 0
                ),
                "deterministic_changes": repair_result.deterministic_changes,
                "diversity_state_before": state_before,
                "diversity_state_after": diversity_state.to_dict(),
                "reports": [
                    report.to_dict()
                    for report in repair_result.reports
                ],
            }
        )

    c5_summary, c5_valid = finalize_repair_summary(
        original_quests=c2_quests,
        initial_valid=c2_valid,
        final_candidates=c5_candidates,
        repair_records=c5_repair_records,
        validators=validators,
        world=app.world,
        generation_diagnostics=c2_generation,
        total_generation_calls=c2_summary["total_generation_calls"],
    )
    c5_summary["diversity_repair_state"] = diversity_state.to_dict()
    results["C5_diversity_aware_repair"] = c5_summary

    save_json(c5_valid, experiment_dir / "C5_final_quests.json")
    save_json(c5_repair_records, experiment_dir / "C5_repair_records.json")
    save_json(
        diversity_state.to_dict(),
        experiment_dir / "C5_diversity_state.json",
    )

    save_json(
        experiment_metadata,
        experiment_dir / "experiment_metadata.json",
    )

    comparison = {
        "experiment_metadata": experiment_metadata,
        "C4": c4_summary["set_metrics_valid_outputs"],
        "C5": c5_summary["set_metrics_valid_outputs"],
        "delta_C5_minus_C4": {
            key: (
                c5_summary["set_metrics_valid_outputs"].get(key, 0)
                - c4_summary["set_metrics_valid_outputs"].get(key, 0)
            )
            for key in (
                "quest_type_entropy",
                "unique_structural_signatures",
                "duplicate_signature_rate",
                "entity_coverage",
                "entity_concentration",
                "average_pairwise_similarity",
            )
        },
    }
    save_json(comparison, experiment_dir / "C4_C5_diversity_comparison.json")

    results_with_metadata = {
        "experiment_metadata": experiment_metadata,
        "configurations": results,
    }
    
    save_json(
        results_with_metadata,
        app.settings.output_dir / "configuration_comparison.json",
    )
    save_json(
        results_with_metadata,
        experiment_dir / "configuration_comparison.json",
    )

    print("\nResumo das taxas comparáveis:")
    print(
        {
            name: data.get("validity_rate")
            for name, data in results.items()
        }
    )
    print("\nComparação de diversidade C4 x C5:")
    print(comparison["delta_C5_minus_C4"])
    print(
        "Resultados detalhados em:",
        app.settings.output_dir / "configuration_comparison.json",
    )


if __name__ == "__main__":
    main()
