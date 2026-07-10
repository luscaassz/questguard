from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, Optional, Set

from questguard.domain.issues import Issue, ValidationReport
from questguard.repositories.world_repository import WorldRepository
from questguard.validation.base import QuestValidator


DEFAULT_ACTION_TARGET_TYPES: Dict[str, Set[str]] = {
    "talk": {"npc"},
    "return": {"npc", "location"},
    "collect": {"item", "object"},
    "deliver": {"npc", "location"},
    "visit": {"location"},
    "travel": {"location"},
    "investigate": {"location", "item", "object", "npc"},
    "inspect": {"location", "item", "object"},
    "interact": {"npc", "item", "object", "location"},
    "defeat": {"enemy", "npc"},
    "protect": {"npc", "location", "object"},
    "rescue": {"npc"},
    "escort": {"npc"},
    "use": {"item", "object"},
    "unlock": {"location", "object"},
}


class ReferentialValidator(QuestValidator):
    name = "referential"

    def __init__(
        self,
        world: WorldRepository,
        action_target_types: Optional[Dict[str, Set[str]]] = None,
    ):
        self.world = world
        self.action_target_types = action_target_types or DEFAULT_ACTION_TARGET_TYPES

    def _validate_typed_reference(
        self,
        report: ValidationReport,
        *,
        entity_id: Any,
        expected_types: Iterable[str],
        path: str,
        code: str,
    ) -> None:
        expected = set(expected_types)
        if not isinstance(entity_id, str) or not entity_id.strip():
            return

        entity_id = entity_id.strip()
        actual_type = self.world.get_entity_type(entity_id)
        if actual_type is None:
            report.issues.append(
                Issue(
                    code="UNKNOWN_ENTITY",
                    severity="error",
                    message=f"A entidade '{entity_id}' não existe no modelo do mundo.",
                    path=path,
                    suggestion="Usar um ID existente ou adicionar a entidade ao world.json.",
                    source=self.name,
                )
            )
            return

        if actual_type not in expected:
            report.issues.append(
                Issue(
                    code=code,
                    severity="error",
                    message=(
                        f"A entidade '{entity_id}' é do tipo '{actual_type}', "
                        f"mas o campo aceita {sorted(expected)}."
                    ),
                    path=path,
                    suggestion="Substituir por uma entidade de categoria compatível.",
                    source=self.name,
                    metadata={"actual_type": actual_type, "expected_types": sorted(expected)},
                )
            )

    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        report = ValidationReport(validator=self.name)

        self._validate_typed_reference(
            report,
            entity_id=quest.get("giver_npc"),
            expected_types={"npc"},
            path="giver_npc",
            code="INVALID_QUEST_GIVER_TYPE",
        )
        self._validate_typed_reference(
            report,
            entity_id=quest.get("start_location"),
            expected_types={"location"},
            path="start_location",
            code="INVALID_START_LOCATION_TYPE",
        )

        objectives = quest.get("objectives", [])
        if isinstance(objectives, list):
            step_ids = [obj.get("step_id") for obj in objectives if isinstance(obj, dict)]
            duplicates = [step for step, count in Counter(step_ids).items() if step and count > 1]
            for step_id in duplicates:
                report.issues.append(
                    Issue(
                        code="DUPLICATE_STEP_ID",
                        severity="error",
                        message=f"O step_id '{step_id}' aparece mais de uma vez.",
                        path="objectives",
                        suggestion="Atribuir um identificador único a cada objetivo.",
                        source=self.name,
                    )
                )

            for index, objective in enumerate(objectives):
                if not isinstance(objective, dict):
                    continue
                action = objective.get("action")
                target = objective.get("target")
                target_path = f"objectives[{index}].target"

                if isinstance(target, str) and target.strip():
                    target_type = self.world.get_entity_type(target.strip())
                    if target_type is None:
                        report.issues.append(
                            Issue(
                                code="INVALID_OR_IMPLICIT_TARGET",
                                severity="error",
                                message=f"O alvo '{target}' não existe no modelo do mundo.",
                                path=target_path,
                                suggestion="Usar um alvo existente e explicitamente modelado.",
                                source=self.name,
                            )
                        )
                    elif isinstance(action, str):
                        expected = self.action_target_types.get(action.strip().lower())
                        if expected and target_type not in expected:
                            report.issues.append(
                                Issue(
                                    code="INCOMPATIBLE_ACTION_TARGET",
                                    severity="error",
                                    message=(
                                        f"A ação '{action}' não é compatível com alvo do tipo "
                                        f"'{target_type}' ({target})."
                                    ),
                                    path=target_path,
                                    suggestion=(
                                        f"Usar um alvo dos tipos {sorted(expected)} ou alterar a ação."
                                    ),
                                    source=self.name,
                                    metadata={
                                        "action": action,
                                        "target_type": target_type,
                                        "expected_types": sorted(expected),
                                    },
                                )
                            )

        rewards = quest.get("rewards", [])
        if isinstance(rewards, list):
            for index, reward in enumerate(rewards):
                if not isinstance(reward, dict):
                    continue
                reward_type = reward.get("type")
                reward_value = reward.get("value")
                if reward_type == "item":
                    self._validate_typed_reference(
                        report,
                        entity_id=reward_value,
                        expected_types={"item"},
                        path=f"rewards[{index}].value",
                        code="INVALID_REWARD_ITEM_TYPE",
                    )

        return report
