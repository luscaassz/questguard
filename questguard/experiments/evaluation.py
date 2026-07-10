from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Sequence

from questguard.experiments.fault_injection import Mutant
from questguard.validation.base import QuestValidator


def _scores(tp: int, fp: int, fn: int, tn: int = 0) -> Dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if tp + tn + fp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def evaluate_fault_detection(
    mutants: Sequence[Mutant],
    validators: Sequence[QuestValidator],
    valid_controls: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    by_validator = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0, "tn": 0})
    by_fault = defaultdict(lambda: {"detected": 0, "total": 0})
    records: List[Dict[str, Any]] = []
    architecture_tp = 0
    architecture_fn = 0

    for mutant in mutants:
        expected = set(mutant.expected_codes)
        union_codes = set()
        validator_codes: Dict[str, List[str]] = {}

        for validator in validators:
            report = validator.validate(mutant.quest)
            reported = {issue.code for issue in report.issues}
            validator_codes[validator.name] = sorted(reported)
            union_codes.update(reported)
            if reported & expected:
                by_validator[validator.name]["tp"] += 1
            else:
                by_validator[validator.name]["fn"] += 1

        detected = bool(union_codes & expected)
        architecture_tp += int(detected)
        architecture_fn += int(not detected)
        by_fault[mutant.fault_type]["detected"] += int(detected)
        by_fault[mutant.fault_type]["total"] += 1
        records.append({
            "mutant_id": mutant.mutant_id,
            "fault_type": mutant.fault_type,
            "expected_codes": sorted(expected),
            "reported_codes_by_validator": validator_codes,
            "reported_codes_union": sorted(union_codes),
            "detected": detected,
        })

    architecture_fp = 0
    architecture_tn = 0
    control_records = []
    for quest in valid_controls:
        union_codes = set()
        validator_codes = {}
        for validator in validators:
            report = validator.validate(quest)
            reported = {issue.code for issue in report.issues}
            validator_codes[validator.name] = sorted(reported)
            union_codes.update(reported)
            if reported:
                by_validator[validator.name]["fp"] += 1
            else:
                by_validator[validator.name]["tn"] += 1
        flagged = bool(union_codes)
        architecture_fp += int(flagged)
        architecture_tn += int(not flagged)
        control_records.append({
            "quest_id": quest.get("quest_id"),
            "reported_codes_by_validator": validator_codes,
            "flagged": flagged,
        })

    validator_metrics = {
        name: _scores(**counts)
        for name, counts in by_validator.items()
    }
    fault_metrics = {
        fault: {
            **counts,
            "detection_rate": counts["detected"] / counts["total"] if counts["total"] else 0.0,
        }
        for fault, counts in by_fault.items()
    }

    return {
        "architecture_metrics": _scores(
            architecture_tp,
            architecture_fp,
            architecture_fn,
            architecture_tn,
        ),
        "metrics_by_validator": validator_metrics,
        "metrics_by_fault_type": fault_metrics,
        "mutant_records": records,
        "control_records": control_records,
    }
