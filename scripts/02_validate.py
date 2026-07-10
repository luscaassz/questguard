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
from questguard.reports.io import load_json, save_json


def resolve_input_path(
    project_root: Path,
    input_path: Path | None,
    default_path: Path,
) -> Path:
    if input_path is None:
        return default_path

    if input_path.is_absolute():
        return input_path

    return project_root / input_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa os quality gates nas quests geradas."
    )

    parser.add_argument(
        "--semantic",
        action="store_true",
        help="Inclui o gate semântico por LLM.",
    )

    parser.add_argument(
        "--show-issues",
        action="store_true",
        help="Mostra no terminal todos os erros e avisos encontrados.",
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Arquivo JSON que será validado. "
            "O padrão é outputs/quests.json."
        ),
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
    )

    args = parser.parse_args()

    project_root = args.project_root.resolve()
    app = build_application(project_root)

    input_path = resolve_input_path(
        project_root=project_root,
        input_path=args.input,
        default_path=app.settings.output_dir / "quests.json",
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"Arquivo de quests não encontrado: {input_path}"
        )

    quests = load_json(input_path)

    if not isinstance(quests, list):
        raise ValueError(
            f"O arquivo {input_path} deve conter uma lista de quests."
        )

    validators = list(app.deterministic_validators)

    if args.semantic:
        validators.append(app.semantic_validator)

    records = []

    validator_summary: Dict[str, Dict[str, int]] = {
        validator.name: {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "warnings": 0,
        }
        for validator in validators
    }

    for index, quest in enumerate(quests, start=1):
        quest_id = quest.get("quest_id", f"unknown_quest_{index}")

        reports = [
            validator.validate(quest)
            for validator in validators
        ]

        combined = combine_reports(reports)

        records.append(
            {
                "quest_id": quest_id,
                "passed": combined.passed,
                "reports": [
                    report.to_dict()
                    for report in reports
                ],
            }
        )

        status = "PASS" if combined.passed else "FAIL"

        print(f"\n[{index}/{len(quests)}] {quest_id}: {status}")

        for report in reports:
            stats = validator_summary[report.validator]

            if report.passed:
                stats["passed"] += 1
            else:
                stats["failed"] += 1

            stats["errors"] += report.error_count
            stats["warnings"] += report.warning_count

            if args.show_issues:
                validator_status = "PASS" if report.passed else "FAIL"
                print(f"  {report.validator}: {validator_status}")

                for issue in report.issues:
                    print(
                        f"    [{issue.severity.upper()}] "
                        f"{issue.code}"
                    )

                    if issue.path:
                        print(f"      Campo: {issue.path}")

                    print(f"      Problema: {issue.message}")

                    if issue.suggestion:
                        print(f"      Sugestão: {issue.suggestion}")

    passed_count = sum(
        1
        for record in records
        if record["passed"]
    )

    summary: Dict[str, Any] = {
        "input_file": str(input_path),
        "total": len(records),
        "passed": passed_count,
        "failed": len(records) - passed_count,
        "acceptance_rate": (
            passed_count / len(records)
            if records
            else 0.0
        ),
        "validators": validator_summary,
    }

    save_json(
        records,
        app.settings.output_dir / "validation_report.json",
    )

    save_json(
        summary,
        app.settings.output_dir / "validation_summary.json",
    )

    print("\n" + "=" * 70)
    print("Resumo da validação")
    print("=" * 70)

    print(f"Arquivo: {input_path}")
    print(f"Total: {summary['total']}")
    print(f"Aprovadas: {summary['passed']}")
    print(f"Rejeitadas: {summary['failed']}")
    print(
        f"Taxa de aceitação: "
        f"{summary['acceptance_rate']:.2%}"
    )

    print("\nResultados por validator:")

    for validator_name, stats in validator_summary.items():
        print(
            f"- {validator_name}: "
            f"{stats['passed']} PASS, "
            f"{stats['failed']} FAIL, "
            f"{stats['errors']} erros, "
            f"{stats['warnings']} avisos"
        )


if __name__ == "__main__":
    main()