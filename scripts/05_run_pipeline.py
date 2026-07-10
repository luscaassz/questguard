from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.bootstrap import build_application
from questguard.orchestration.pipeline import QuestPipeline
from questguard.reports.io import save_csv, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa geração, validação, reparo e análise.")
    parser.add_argument("--batches", type=int, default=10)
    parser.add_argument("--quests-per-batch", type=int, default=10)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    app = build_application(args.project_root, include_semantic_in_repair=args.semantic)
    validators = app.deterministic_validators + ([app.semantic_validator] if args.semantic else [])
    pipeline = QuestPipeline(
        world=app.world,
        generation_service=app.generation_service,
        validators=validators,
        repair_orchestrator=app.repair_orchestrator,
    )
    result = pipeline.run(
        batches=args.batches,
        quests_per_batch=args.quests_per_batch,
        repair=args.repair,
    )

    out = app.settings.output_dir
    save_json(result.generated, out / "pipeline_generated.json")
    save_json(result.accepted, out / "pipeline_accepted.json")
    save_json(result.rejected, out / "pipeline_rejected.json")
    save_json(result.validation_records, out / "pipeline_validation.json")
    save_json(result.repair_records, out / "pipeline_repairs.json")
    save_csv(result.graph_metrics, out / "pipeline_graph_metrics.csv")
    save_json(result.set_metrics, out / "pipeline_set_metrics.json")
    print({
        "generated": len(result.generated),
        "accepted": len(result.accepted),
        "rejected": len(result.rejected),
    })


if __name__ == "__main__":
    main()
