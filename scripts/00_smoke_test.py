from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.bootstrap import build_application
from questguard.domain.issues import combine_reports
from questguard.reports.io import load_json


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    app = build_application(project_root)
    quest = load_json(project_root / "data" / "example_valid_quest.json")
    reports = [validator.validate(quest) for validator in app.deterministic_validators]
    combined = combine_reports(reports)
    for report in reports:
        print(f"{report.validator}: {'PASS' if report.passed else 'FAIL'}")
        for issue in report.issues:
            print(f"  - {issue.severity}: {issue.code} — {issue.message}")
    print(f"Resultado final: {'PASS' if combined.passed else 'FAIL'}")


if __name__ == "__main__":
    main()
