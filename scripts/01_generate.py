from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from questguard.analysis.diversity_metrics import structural_signature
from questguard.bootstrap import build_application
from questguard.reports.io import load_json, save_json, save_text


def valid_existing_batch(path: Path, expected_size: int) -> bool:
    if not path.exists():
        return False
    try:
        data = load_json(path)
        return isinstance(data, list) and len(data) == expected_size and all(
            isinstance(quest, dict) for quest in data
        )
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera quests em batches usando Ollama.")
    parser.add_argument("--batches", type=int, default=10)
    parser.add_argument("--quests-per-batch", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="Regenera batches já existentes.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    app = build_application(args.project_root)
    batch_dir = app.settings.output_dir / "quest_batches"
    raw_dir = app.settings.output_dir / "raw_responses"
    all_quests = []
    forbidden_signatures = []

    for batch_index in range(1, args.batches + 1):
        batch_path = batch_dir / f"batch_{batch_index:02d}.json"
        if not args.force and valid_existing_batch(batch_path, args.quests_per_batch):
            existing = load_json(batch_path)
            all_quests.extend(existing)
            forbidden_signatures.extend(
                signature
                for quest in existing
                if (signature := structural_signature(quest, app.world))
            )
            print(f"Batch {batch_index:02d} já existe e foi reutilizado.")
            continue

        batch = app.generation_service.generate_batch(
            batch_index=batch_index,
            number_of_quests=args.quests_per_batch,
            forbidden_signatures=forbidden_signatures,
        )
        save_json(batch.quests, batch_path)
        save_text(batch.raw_response, raw_dir / f"batch_{batch_index:02d}.txt")
        all_quests.extend(batch.quests)
        forbidden_signatures.extend(
            signature
            for quest in batch.quests
            if (signature := structural_signature(quest, app.world))
        )
        print(f"Batch {batch_index:02d}: {len(batch.quests)} quests salvas.")

    save_json(all_quests, app.settings.output_dir / "quests.json")
    print(f"Total consolidado: {len(all_quests)} quests.")


if __name__ == "__main__":
    main()
