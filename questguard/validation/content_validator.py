from __future__ import annotations

import re
from typing import Any, Dict

from questguard.domain.issues import Issue, ValidationReport
from questguard.validation.base import QuestValidator


GENERIC_COMPLETION_PATTERNS = (
    r"complet\w*.*(todos|os).*(objetivos|passos)",
    r"finaliz(ar|e|ou).*(a|esta).*(quest|miss[aã]o)",
)
WEAK_PRECONDITION_PATTERNS = (
    r"est[aá] dispon[ií]vel",
    r"est[aá] acess[ií]vel",
    r"pode iniciar",
)


class ContentRuleValidator(QuestValidator):
    name = "content_rules"

    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        report = ValidationReport(validator=self.name)

        completion_conditions = quest.get("completion_conditions", [])
        if isinstance(completion_conditions, list):
            for index, condition in enumerate(completion_conditions):
                text = str(condition).strip().lower()
                if any(re.search(pattern, text) for pattern in GENERIC_COMPLETION_PATTERNS):
                    report.issues.append(
                        Issue(
                            code="GENERIC_COMPLETION_CONDITION",
                            severity="error",
                            message="A condição de conclusão apenas repete que os objetivos devem ser concluídos.",
                            path=f"completion_conditions[{index}]",
                            suggestion="Definir um estado observável, entidade, local ou evento final específico.",
                            source=self.name,
                        )
                    )

        preconditions = quest.get("preconditions", [])
        if isinstance(preconditions, list):
            for index, condition in enumerate(preconditions):
                text = str(condition).strip().lower()
                if any(re.search(pattern, text) for pattern in WEAK_PRECONDITION_PATTERNS):
                    report.issues.append(
                        Issue(
                            code="WEAK_PRECONDITION",
                            severity="warning",
                            message="A precondição não define um estado verificável de forma precisa.",
                            path=f"preconditions[{index}]",
                            suggestion="Usar uma condição estruturada ou um estado explícito do mundo.",
                            source=self.name,
                        )
                    )

        objectives = quest.get("objectives", [])
        if isinstance(objectives, list):
            for index, objective in enumerate(objectives):
                if not isinstance(objective, dict):
                    continue
                success = str(objective.get("success_condition", "")).strip()
                if len(success) < 12:
                    report.issues.append(
                        Issue(
                            code="UNCLEAR_SUCCESS_CONDITION",
                            severity="warning",
                            message="A condição de sucesso é curta ou pouco específica.",
                            path=f"objectives[{index}].success_condition",
                            suggestion="Definir uma condição observável e testável.",
                            source=self.name,
                        )
                    )

        return report
