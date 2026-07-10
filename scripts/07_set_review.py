from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.analysis.set_reviewer import SetReviewer
from questguard.bootstrap import build_application
from questguard.reports.io import load_json, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Avalia o conjunto completo de quests.")
    parser.add_argument("--input", default="accepted_quests.json")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    app = build_application(args.project_root)
    input_path = app.settings.output_dir / args.input
    if not input_path.exists():
        input_path = app.settings.output_dir / "quests.json"
    quests = load_json(input_path)
    reviewer = SetReviewer(llm=app.llm, settings=app.settings, world=app.world)
    result = reviewer.review(quests)
    save_json(result, app.settings.output_dir / "quest_set_review.json")
    print(result.get("overall_set_score"))


if __name__ == "__main__":
    main()
