from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.analysis.diversity_metrics import compute_set_metrics
from questguard.analysis.graph_metrics import compute_graph_metrics
from questguard.bootstrap import build_application
from questguard.reports.io import load_json, save_csv, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula métricas de grafo e diversidade.")
    parser.add_argument("--input", default="accepted_quests.json")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    app = build_application(args.project_root)
    input_path = app.settings.output_dir / args.input
    if not input_path.exists():
        input_path = app.settings.output_dir / "quests.json"
    quests = load_json(input_path)

    graph_rows = [compute_graph_metrics(quest, app.world) for quest in quests]
    set_metrics = compute_set_metrics(quests, app.world)
    save_csv(graph_rows, app.settings.output_dir / "quest_graph_metrics.csv")
    save_json(set_metrics, app.settings.output_dir / "quest_set_metrics.json")
    print(f"Métricas calculadas para {len(quests)} quests.")


if __name__ == "__main__":
    main()
