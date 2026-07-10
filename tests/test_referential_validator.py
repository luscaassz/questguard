from __future__ import annotations

import copy

from questguard.validation.referential_validator import ReferentialValidator


def test_accepts_valid_references(world, valid_quest):
    report = ReferentialValidator(world).validate(valid_quest)
    assert report.passed


def test_rejects_item_as_giver(world, valid_quest):
    quest = copy.deepcopy(valid_quest)
    quest["giver_npc"] = "item_mapa_antigo"
    report = ReferentialValidator(world).validate(quest)
    assert any(issue.code == "INVALID_QUEST_GIVER_TYPE" for issue in report.issues)


def test_rejects_incompatible_action_target(world, valid_quest):
    quest = copy.deepcopy(valid_quest)
    quest["objectives"][0]["action"] = "collect"
    report = ReferentialValidator(world).validate(quest)
    assert any(issue.code == "INCOMPATIBLE_ACTION_TARGET" for issue in report.issues)
