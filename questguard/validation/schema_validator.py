from __future__ import annotations

from typing import Any, Dict

from jsonschema import Draft202012Validator

from questguard.domain.issues import Issue, ValidationReport
from questguard.validation.base import QuestValidator


class SchemaValidator(QuestValidator):
    name = "schema"

    def __init__(self, schema: Dict[str, Any]):
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        report = ValidationReport(validator=self.name)
        errors = sorted(
            self.validator.iter_errors(quest),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        for error in errors:
            path = ".".join(str(part) for part in error.absolute_path)
            report.issues.append(
                Issue(
                    code="SCHEMA_VIOLATION",
                    severity="error",
                    message=error.message,
                    path=path,
                    suggestion="Ajustar o campo para cumprir o JSON Schema.",
                    source=self.name,
                    metadata={"validator": error.validator},
                )
            )
        return report
