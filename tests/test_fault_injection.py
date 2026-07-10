from __future__ import annotations

from questguard.experiments.evaluation import evaluate_fault_detection
from questguard.experiments.fault_injection import inject_faults
from questguard.validation.content_validator import ContentRuleValidator
from questguard.validation.graph_validator import GraphValidator
from questguard.validation.referential_validator import ReferentialValidator
from questguard.validation.schema_validator import SchemaValidator


def test_fault_injection_produces_mutants(valid_quest):
    mutants = inject_faults([valid_quest])
    assert len(mutants) == 7


def test_fault_detection_evaluation(schema, world, valid_quest):
    mutants = inject_faults([valid_quest])
    validators = [
        SchemaValidator(schema),
        ReferentialValidator(world),
        GraphValidator(),
        ContentRuleValidator(),
    ]
    result = evaluate_fault_detection(mutants, validators)
    assert "schema" in result["metrics_by_validator"]
    assert result["mutant_records"]
