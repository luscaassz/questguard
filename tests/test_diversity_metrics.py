from __future__ import annotations

import copy

from questguard.analysis.diversity_metrics import compute_set_metrics, structural_signature


def test_structural_signature_is_stable(world, valid_quest):
    signature = structural_signature(valid_quest, world)
    assert signature == "talk:npc -> visit:location -> collect:item -> return:npc"


def test_duplicate_signature_rate(world, valid_quest):
    second = copy.deepcopy(valid_quest)
    second["quest_id"] = "batch_01_quest_002"
    metrics = compute_set_metrics([valid_quest, second], world)
    assert metrics["duplicate_signature_rate"] == 1.0
