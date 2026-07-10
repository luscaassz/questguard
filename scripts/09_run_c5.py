from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.analysis.diversity_metrics import compute_set_metrics, structural_signature
from questguard.bootstrap import build_application
from questguard.domain.issues import combine_reports
from questguard.repair.diversity_aware import (
    DiversityAwareQuestRepairer,
    DiversityRepairState,
)
from questguard.repair.orchestrator import RepairOrchestrator
from questguard.reports.io import load_json, save_json


def resolve_path(project_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else project_root / value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Executa somente o C5 sobre quests C2 já geradas, sem chamar "
            "novamente os geradores C1 e C2."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("outputs/configuration_experiment/C2_schema_guided_quests.json"),
    )
    parser.add_argument(
        "--c4-input",
        type=Path,
        default=Path("outputs/configuration_experiment/C4_final_quests.json"),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    input_path = resolve_path(project_root, args.input)
    c4_path = resolve_path(project_root, args.c4_input)

    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo C2 não encontrado: {input_path}")

    app = build_application(project_root)
    c2_quests = load_json(input_path)
    if not isinstance(c2_quests, list):
        raise ValueError("O arquivo C2 deve conter uma lista de quests.")

    initial_valid: List[Dict[str, Any]] = []
    initial_invalid: List[Dict[str, Any]] = []
    for quest in c2_quests:
        reports = [
            validator.validate(quest)
            for validator in app.deterministic_validators
        ]
        (initial_valid if combine_reports(reports).passed else initial_invalid).append(quest)

    state = DiversityRepairState.from_quests(initial_valid, app.world)
    repairer = DiversityAwareQuestRepairer(
        world=app.world,
        schema=app.schema,
        state=state,
    )
    orchestrator = RepairOrchestrator(
        llm=app.llm,
        settings=app.settings,
        world=app.world,
        schema=app.schema,
        validators=app.deterministic_validators,
        deterministic_repairer=repairer,
    )

    final_quests = list(initial_valid)
    records: List[Dict[str, Any]] = []

    for index, quest in enumerate(initial_invalid, start=1):
        quest_id = quest.get("quest_id", f"unknown_{index}")
        print(f"[{index}/{len(initial_invalid)}] C5 reparando {quest_id}...")

        state_before = state.to_dict()
        before_signature = structural_signature(quest, app.world)
        result = orchestrator.repair(quest)
        passed = combine_reports(result.reports).passed
        after_signature = structural_signature(result.final_quest, app.world)

        if passed:
            final_quests.append(result.final_quest)
            state.register(result.final_quest, app.world)

        records.append(
            {
                "quest_id": quest_id,
                "passed_after_repair": passed,
                "llm_attempts": result.attempts,
                "before_signature": before_signature,
                "after_signature": after_signature,
                "signature_was_already_used": (
                    state_before["signature_counts"].get(after_signature, 0) > 0
                ),
                "deterministic_changes": result.deterministic_changes,
                "reports": [report.to_dict() for report in result.reports],
                "diversity_state_before": state_before,
                "diversity_state_after": state.to_dict(),
            }
        )
        print(f"  Resultado: {'PASS' if passed else 'FAIL'}")
        print(f"  Assinatura: {before_signature} -> {after_signature}")

    output_dir = app.settings.output_dir / "configuration_experiment"
    c5_path = output_dir / "C5_final_quests.json"
    metrics_path = output_dir / "C5_set_metrics.json"
    records_path = output_dir / "C5_repair_records.json"
    state_path = output_dir / "C5_diversity_state.json"

    c5_metrics = compute_set_metrics(final_quests, app.world)
    save_json(final_quests, c5_path)
    save_json(c5_metrics, metrics_path)
    save_json(records, records_path)
    save_json(state.to_dict(), state_path)

    summary: Dict[str, Any] = {
        "original_generated_count": len(c2_quests),
        "initial_valid_count": len(initial_valid),
        "repair_attempted_quests": len(initial_invalid),
        "repair_successes": sum(int(record["passed_after_repair"]) for record in records),
        "final_valid_count": len(final_quests),
        "final_yield": len(final_quests) / len(c2_quests) if c2_quests else 0.0,
        "total_llm_repair_calls": sum(record["llm_attempts"] for record in records),
        "set_metrics": c5_metrics,
    }

    if c4_path.exists():
        c4_quests = load_json(c4_path)
        if isinstance(c4_quests, list):
            c4_metrics = compute_set_metrics(c4_quests, app.world)
            summary["C4_metrics"] = c4_metrics
            summary["delta_C5_minus_C4"] = {
                key: c5_metrics.get(key, 0) - c4_metrics.get(key, 0)
                for key in (
                    "quest_type_entropy",
                    "unique_structural_signatures",
                    "duplicate_signature_rate",
                    "entity_coverage",
                    "entity_concentration",
                    "average_pairwise_similarity",
                )
            }

    summary_path = output_dir / "C5_summary.json"
    save_json(summary, summary_path)

    print("\nC5 concluído.")
    print(f"Quests finais: {c5_path}")
    print(f"Métricas: {metrics_path}")
    print(f"Resumo: {summary_path}")
    if "delta_C5_minus_C4" in summary:
        print("Delta C5 - C4:")
        print(summary["delta_C5_minus_C4"])


if __name__ == "__main__":
    main()
