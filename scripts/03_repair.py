from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.bootstrap import build_application
from questguard.domain.issues import combine_reports
from questguard.reports.io import load_json, save_json, save_text


def resolve_path(project_root: Path, value: Path | None, default: Path) -> Path:
    if value is None:
        return default
    return value if value.is_absolute() else project_root / value


def print_reports(reports: list, indentation: str = "    ") -> None:
    for report in reports:
        status = "PASS" if report.passed else "FAIL"
        print(f"{indentation}{report.validator}: {status}")
        for issue in report.issues:
            print(f"{indentation}  [{issue.severity.upper()}] {issue.code}")
            if issue.path:
                print(f"{indentation}    Campo: {issue.path}")
            print(f"{indentation}    Problema: {issue.message}")
            if issue.suggestion:
                print(f"{indentation}    Sugestão: {issue.suggestion}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repara quests rejeitadas e executa novamente os quality gates."
    )
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--show-issues", action="store_true")
    parser.add_argument("--show-changes", action="store_true")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    app = build_application(project_root, include_semantic_in_repair=args.semantic)
    input_path = resolve_path(
        project_root,
        args.input,
        app.settings.output_dir / "quests.json",
    )

    quests = load_json(input_path)
    if not isinstance(quests, list):
        raise ValueError(f"O arquivo {input_path} deve conter uma lista de quests.")

    accepted: list[Dict[str, Any]] = []
    rejected: list[Dict[str, Any]] = []
    records: list[Dict[str, Any]] = []
    raw_dir = app.settings.output_dir / "repair_raw_responses"

    print("=" * 70)
    print("QuestGuard — reparo híbrido")
    print("=" * 70)
    print(f"Entrada: {input_path}")
    print(f"Quests encontradas: {len(quests)}")
    print(f"Gate semântico: {'ativado' if args.semantic else 'desativado'}")

    for index, quest in enumerate(quests, start=1):
        quest_id = quest.get("quest_id", f"unknown_quest_{index}")
        print("\n" + "-" * 70)
        print(f"[{index}/{len(quests)}] Reparando {quest_id}")

        result = app.repair_orchestrator.repair(quest)
        passed = combine_reports(result.reports).passed
        (accepted if passed else rejected).append(result.final_quest)

        records.append(
            {
                "quest_id": quest_id,
                "llm_attempts": result.attempts,
                "repaired": result.repaired,
                "passed": passed,
                "deterministic_changes": result.deterministic_changes,
                "final_quest": result.final_quest,
                "reports": [report.to_dict() for report in result.reports],
            }
        )

        for attempt, raw in enumerate(result.raw_responses, start=1):
            save_text(raw, raw_dir / f"{quest_id}_attempt_{attempt}.txt")

        print(f"Correções determinísticas: {len(result.deterministic_changes)}")
        print(f"Tentativas com LLM: {result.attempts}")
        print(f"Resultado: {'PASS' if passed else 'FAIL'}")

        if args.show_changes:
            for change in result.deterministic_changes:
                print(f"    [FIX] {change['code']} — {change['path']}")
                print(f"      Motivo: {change['reason']}")

        if args.show_issues or not passed:
            print_reports(result.reports)

    accepted_path = app.settings.output_dir / "accepted_quests.json"
    rejected_path = app.settings.output_dir / "rejected_quests.json"
    report_path = app.settings.output_dir / "repair_report.json"

    save_json(accepted, accepted_path)
    save_json(rejected, rejected_path)
    save_json(records, report_path)

    total = len(quests)
    rate = len(accepted) / total if total else 0.0
    print("\n" + "=" * 70)
    print("Resumo do reparo")
    print("=" * 70)
    print(f"Total: {total}")
    print(f"Aprovadas: {len(accepted)}")
    print(f"Rejeitadas: {len(rejected)}")
    print(f"Taxa final de aprovação: {rate:.2%}")
    print(f"Quests aprovadas: {accepted_path}")
    print(f"Quests rejeitadas: {rejected_path}")
    print(f"Relatório: {report_path}")


if __name__ == "__main__":
    main()
