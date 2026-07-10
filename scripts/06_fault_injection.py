from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.bootstrap import build_application
from questguard.experiments.evaluation import evaluate_fault_detection
from questguard.experiments.fault_injection import inject_faults
from questguard.reports.io import load_json, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Injeta falhas e avalia a detecção dos quality gates.")
    parser.add_argument("--input", default="accepted_quests.json")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    app = build_application(args.project_root)
    input_path = app.settings.output_dir / args.input
    if not input_path.exists():
        input_path = app.settings.output_dir / "quests.json"
    quests = load_json(input_path)[: args.limit]
    mutants = inject_faults(quests)
    evaluation = evaluate_fault_detection(
        mutants, app.deterministic_validators, valid_controls=quests
    )

    save_json([
        {
            "mutant_id": mutant.mutant_id,
            "fault_type": mutant.fault_type,
            "expected_codes": mutant.expected_codes,
            "quest": mutant.quest,
        }
        for mutant in mutants
    ], app.settings.output_dir / "fault_mutants.json")
    save_json(evaluation, app.settings.output_dir / "fault_detection_evaluation.json")
    print(evaluation["metrics_by_validator"])


if __name__ == "__main__":
    main()
