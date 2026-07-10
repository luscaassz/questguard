from __future__ import annotations

import copy

from questguard.validation.graph_validator import GraphValidator


def test_accepts_acyclic_dependencies(valid_quest):
    report = GraphValidator().validate(valid_quest)
    assert report.passed


def test_detects_missing_dependency(valid_quest):
    quest = copy.deepcopy(valid_quest)
    quest["objectives"][1]["depends_on"] = ["step_999"]
    report = GraphValidator().validate(quest)
    assert any(issue.code == "MISSING_STEP_DEPENDENCY" for issue in report.issues)


def test_detects_cycle(valid_quest):
    quest = copy.deepcopy(valid_quest)
    quest["objectives"][0]["depends_on"] = ["step_002"]
    quest["objectives"][1]["depends_on"] = ["step_001"]
    report = GraphValidator().validate(quest)
    assert any(issue.code == "CYCLIC_OBJECTIVE_DEPENDENCY" for issue in report.issues)
