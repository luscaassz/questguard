from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from statistics import mean, stdev
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = PROJECT_ROOT / "outputs" / "experiments"

RUN_NAMES = [
    "final_30_run_01",
    "final_30_run_02",
    "final_30_run_03",
]

CONFIGURATION_NAMES = [
    "C1_prompt_only",
    "C2_schema_guided",
    "C3_quality_gates",
    "C4_quality_gates_repair",
    "C5_diversity_aware_repair",
]

CONFIGURATION_METRICS = [
    "validity_rate",
    "initial_validity_rate",
    "final_yield_over_original_generation",
    "repair_success_rate",
    "average_errors_per_quest",
    "average_warnings_per_quest",
    "total_generation_calls",
    "total_llm_repair_calls",
]

DIVERSITY_METRICS = [
    "quest_type_entropy",
    "unique_structural_signatures",
    "duplicate_signature_rate",
    "entity_coverage",
    "entity_concentration",
    "average_pairwise_similarity",
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "values": [],
        }

    return {
        "count": len(values),
        "mean": mean(values),
        "standard_deviation": (
            stdev(values) if len(values) > 1 else 0.0
        ),
        "minimum": min(values),
        "maximum": max(values),
        "values": values,
    }


def extract_configurations(
    comparison: dict[str, Any],
) -> dict[str, Any]:
    configurations = comparison.get("configurations")

    if isinstance(configurations, dict):
        return configurations

    # Compatibilidade com a estrutura antiga.
    return {
        key: value
        for key, value in comparison.items()
        if key in CONFIGURATION_NAMES
    }


def main() -> None:
    configuration_rows: list[dict[str, Any]] = []
    diversity_rows: list[dict[str, Any]] = []
    integrity_records: list[dict[str, Any]] = []

    configuration_values: dict[
        str,
        dict[str, list[float]],
    ] = {
        configuration: {
            metric: []
            for metric in CONFIGURATION_METRICS
        }
        for configuration in CONFIGURATION_NAMES
    }

    diversity_values: dict[
        str,
        dict[str, list[float]],
    ] = {
        configuration: {
            metric: []
            for metric in DIVERSITY_METRICS
        }
        for configuration in ("C4", "C5", "delta_C5_minus_C4")
    }

    seeds: list[int] = []
    c2_hashes: list[str] = []
    c5_hashes: list[str] = []

    for run_name in RUN_NAMES:
        run_dir = EXPERIMENTS_DIR / run_name

        comparison_path = run_dir / "configuration_comparison.json"
        diversity_path = run_dir / "C4_C5_diversity_comparison.json"
        metadata_path = run_dir / "experiment_metadata.json"

        required_paths = [
            comparison_path,
            diversity_path,
            metadata_path,
            run_dir / "C2_schema_guided_quests.json",
            run_dir / "C5_final_quests.json",
        ]

        missing = [
            str(path)
            for path in required_paths
            if not path.exists()
        ]

        if missing:
            raise FileNotFoundError(
                f"Arquivos ausentes em {run_name}: {missing}"
            )

        comparison = load_json(comparison_path)
        diversity = load_json(diversity_path)
        metadata = load_json(metadata_path)

        seed = metadata.get("run_seed")
        if isinstance(seed, int):
            seeds.append(seed)

        c2_hash = file_hash(
            run_dir / "C2_schema_guided_quests.json"
        )
        c5_hash = file_hash(
            run_dir / "C5_final_quests.json"
        )

        c2_hashes.append(c2_hash)
        c5_hashes.append(c5_hash)

        integrity_records.append(
            {
                "run": run_name,
                "run_seed": seed,
                "c2_hash": c2_hash,
                "c5_hash": c5_hash,
                "generation_temperature": metadata.get(
                    "generation_temperature"
                ),
                "top_p": metadata.get("top_p"),
                "batches": metadata.get("batches"),
                "quests_per_batch": metadata.get(
                    "quests_per_batch"
                ),
            }
        )

        configurations = extract_configurations(comparison)

        for configuration_name in CONFIGURATION_NAMES:
            configuration = configurations.get(
                configuration_name,
                {},
            )

            row: dict[str, Any] = {
                "run": run_name,
                "run_seed": seed,
                "configuration": configuration_name,
            }

            for metric in CONFIGURATION_METRICS:
                value = configuration.get(metric)
                row[metric] = value

                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    configuration_values[
                        configuration_name
                    ][metric].append(float(value))

            configuration_rows.append(row)

        for diversity_configuration in (
            "C4",
            "C5",
            "delta_C5_minus_C4",
        ):
            metrics = diversity.get(
                diversity_configuration,
                {},
            )

            row = {
                "run": run_name,
                "run_seed": seed,
                "configuration": diversity_configuration,
            }

            for metric in DIVERSITY_METRICS:
                value = metrics.get(metric)
                row[metric] = value

                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    diversity_values[
                        diversity_configuration
                    ][metric].append(float(value))

            diversity_rows.append(row)

    configuration_summary = {
        configuration: {
            metric: numeric_summary(values)
            for metric, values in metrics.items()
            if values
        }
        for configuration, metrics in configuration_values.items()
    }

    diversity_summary = {
        configuration: {
            metric: numeric_summary(values)
            for metric, values in metrics.items()
            if values
        }
        for configuration, metrics in diversity_values.items()
    }

    summary = {
        "run_count": len(RUN_NAMES),
        "run_names": RUN_NAMES,
        "run_seeds": seeds,
        "integrity": {
            "all_seeds_unique": len(set(seeds)) == len(seeds),
            "all_C2_hashes_unique": (
                len(set(c2_hashes)) == len(c2_hashes)
            ),
            "all_C5_hashes_unique": (
                len(set(c5_hashes)) == len(c5_hashes)
            ),
            "records": integrity_records,
        },
        "configuration_metrics": configuration_summary,
        "diversity_metrics": diversity_summary,
    }

    output_json = (
        EXPERIMENTS_DIR
        / "final_30_aggregate_summary.json"
    )

    output_config_csv = (
        EXPERIMENTS_DIR
        / "final_30_configuration_metrics.csv"
    )

    output_diversity_csv = (
        EXPERIMENTS_DIR
        / "final_30_diversity_metrics.csv"
    )

    with output_json.open("w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with output_config_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        fieldnames = [
            "run",
            "run_seed",
            "configuration",
            *CONFIGURATION_METRICS,
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(configuration_rows)

    with output_diversity_csv.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        fieldnames = [
            "run",
            "run_seed",
            "configuration",
            *DIVERSITY_METRICS,
        ]

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(diversity_rows)

    print("=" * 70)
    print("Consolidação concluída")
    print("=" * 70)
    print(f"Runs analisadas: {len(RUN_NAMES)}")
    print(
        "Seeds distintas:",
        summary["integrity"]["all_seeds_unique"],
    )
    print(
        "C2 distintos:",
        summary["integrity"]["all_C2_hashes_unique"],
    )
    print(
        "C5 distintos:",
        summary["integrity"]["all_C5_hashes_unique"],
    )
    print(f"Resumo JSON: {output_json}")
    print(f"Métricas de configuração: {output_config_csv}")
    print(f"Métricas de diversidade: {output_diversity_csv}")


if __name__ == "__main__":
    main()