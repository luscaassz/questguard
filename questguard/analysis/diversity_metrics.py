from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from questguard.repositories.world_repository import WorldRepository


def referenced_entities(quest: Dict[str, Any], world: WorldRepository) -> List[str]:
    candidates: List[Any] = [quest.get("giver_npc"), quest.get("start_location")]
    for objective in quest.get("objectives", []):
        if isinstance(objective, dict):
            candidates.append(objective.get("target"))
    for reward in quest.get("rewards", []):
        if isinstance(reward, dict) and reward.get("type") == "item":
            candidates.append(reward.get("value"))
    return [value for value in candidates if isinstance(value, str) and world.has_entity(value)]


def structural_signature(quest: Dict[str, Any], world: WorldRepository) -> str:
    sequence: List[str] = []
    for objective in quest.get("objectives", []):
        if not isinstance(objective, dict):
            continue
        action = str(objective.get("action", "unknown")).strip().lower()
        target = objective.get("target")
        target_type = world.get_entity_type(target) if isinstance(target, str) else None
        sequence.append(f"{action}:{target_type or 'unknown'}")
    return " -> ".join(sequence)


def _normalized_entropy(values: Sequence[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    if len(counts) <= 1:
        return 0.0
    total = len(values)
    entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
    return entropy / math.log(len(counts))


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def compute_set_metrics(quests: List[Dict[str, Any]], world: WorldRepository) -> Dict[str, Any]:
    quest_types = [str(quest.get("quest_type", "unknown")) for quest in quests]
    signatures = [structural_signature(quest, world) for quest in quests]
    signature_counts = Counter(signatures)
    all_entities = [entity for quest in quests for entity in referenced_entities(quest, world)]
    entity_counts = Counter(all_entities)

    pairwise_similarities: List[float] = []
    for index, quest_a in enumerate(quests):
        features_a = set(quest_a.get("reusable_tags", [])) | set(
            structural_signature(quest_a, world).split(" -> ")
        )
        for quest_b in quests[index + 1 :]:
            features_b = set(quest_b.get("reusable_tags", [])) | set(
                structural_signature(quest_b, world).split(" -> ")
            )
            pairwise_similarities.append(_jaccard(features_a, features_b))

    repeated_quests = sum(count for count in signature_counts.values() if count > 1)
    total_refs = len(all_entities)
    return {
        "quest_count": len(quests),
        "quest_type_entropy": _normalized_entropy(quest_types),
        "unique_structural_signatures": len(signature_counts),
        "duplicate_signature_rate": repeated_quests / len(quests) if quests else 0.0,
        "entity_coverage": world.coverage(all_entities),
        "entity_concentration": max(entity_counts.values()) / total_refs if total_refs else 0.0,
        "average_pairwise_similarity": (
            sum(pairwise_similarities) / len(pairwise_similarities)
            if pairwise_similarities
            else 0.0
        ),
        "quest_type_counts": dict(quest_type_counts := Counter(quest_types)),
        "structural_signature_counts": dict(signature_counts),
        "entity_usage_counts": dict(entity_counts),
    }
