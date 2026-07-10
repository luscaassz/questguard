from __future__ import annotations

import copy

from questguard.validation.schema_validator import SchemaValidator


def test_accepts_valid_quest(schema, valid_quest):
    report = SchemaValidator(schema).validate(valid_quest)
    assert report.passed


def test_rejects_missing_title(schema, valid_quest):
    quest = copy.deepcopy(valid_quest)
    quest.pop("title")
    report = SchemaValidator(schema).validate(quest)
    assert not report.passed
    assert any(issue.code == "SCHEMA_VIOLATION" for issue in report.issues)
