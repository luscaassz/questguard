from __future__ import annotations

import copy
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from questguard.repositories.world_repository import WorldRepository
from questguard.validation.referential_validator import DEFAULT_ACTION_TARGET_TYPES


@dataclass(frozen=True)
class RepairChange:
    code: str
    path: str
    before: Any
    after: Any
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DeterministicQuestRepairer:
    """Applies safe, reproducible repairs before and after LLM repair.

    The component handles errors that do not require creative interpretation:
    missing required values, invalid entity categories, objective cardinality,
    step numbering, dependency cycles, short conditions, tags and design notes.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        schema: Dict[str, Any],
    ) -> None:
        self.world = world
        self.schema = schema

    def repair(
        self,
        quest: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[RepairChange]]:
        current = copy.deepcopy(quest)
        changes: List[RepairChange] = []

        self._repair_scalar_fields(current, changes)
        self._repair_core_references(current, changes)
        self._repair_objectives(current, changes)
        self._repair_preconditions(current, changes)
        self._repair_completion_conditions(current, changes)
        self._repair_rewards(current, changes)
        self._repair_tags(current, changes)
        self._repair_design_notes(current, changes)

        return current, changes

    def _record(
        self,
        changes: List[RepairChange],
        *,
        code: str,
        path: str,
        before: Any,
        after: Any,
        reason: str,
    ) -> None:
        if before == after:
            return
        changes.append(
            RepairChange(
                code=code,
                path=path,
                before=before,
                after=after,
                reason=reason,
            )
        )

    def _schema_property(self, name: str) -> Dict[str, Any]:
        return self.schema.get("properties", {}).get(name, {})

    def _array_min_items(self, name: str, default: int = 0) -> int:
        value = self._schema_property(name).get("minItems", default)
        return value if isinstance(value, int) and value >= 0 else default

    def _array_max_items(self, name: str) -> Optional[int]:
        value = self._schema_property(name).get("maxItems")
        return value if isinstance(value, int) and value >= 0 else None

    def _string_min_length(
        self,
        property_path: Sequence[str],
        default: int = 1,
    ) -> int:
        node: Any = self.schema
        for part in property_path:
            if not isinstance(node, dict):
                return default
            node = node.get(part, {})
        value = node.get("minLength", default) if isinstance(node, dict) else default
        return value if isinstance(value, int) and value >= 0 else default

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _slug(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text.lower()).strip("_")
        return slug or "quest"

    def _first_entity_id(
        self,
        entity_type: str,
        *,
        exclude: Optional[Set[str]] = None,
    ) -> Optional[str]:
        excluded = exclude or set()
        for entity_id in sorted(self.world.ids(entity_type)):
            if entity_id not in excluded:
                return entity_id
        return None

    def _repair_scalar_fields(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        quest_id = self._clean_text(quest.get("quest_id")) or "quest_repaired_001"
        if quest.get("quest_id") != quest_id:
            self._record(
                changes,
                code="FILL_QUEST_ID",
                path="quest_id",
                before=quest.get("quest_id"),
                after=quest_id,
                reason="Quest IDs cannot be empty.",
            )
            quest["quest_id"] = quest_id

        title = self._clean_text(quest.get("title"))
        if len(title) < 3:
            replacement = "Missão restaurada"
            self._record(
                changes,
                code="FILL_TITLE",
                path="title",
                before=quest.get("title"),
                after=replacement,
                reason="The schema requires a non-empty title.",
            )
            quest["title"] = replacement

        summary_min = self._string_min_length(
            ("properties", "summary"),
            default=20,
        )
        summary = self._clean_text(quest.get("summary"))
        if len(summary) < summary_min:
            title = self._clean_text(quest.get("title")) or "esta missão"
            replacement = f"O jogador deve concluir os objetivos definidos para {title}."
            self._record(
                changes,
                code="EXPAND_SUMMARY",
                path="summary",
                before=quest.get("summary"),
                after=replacement,
                reason="The summary did not meet the schema minimum length.",
            )
            quest["summary"] = replacement

        allowed_types = set(
            self._schema_property("quest_type").get("enum", [])
        )
        quest_type = self._clean_text(quest.get("quest_type"))
        if allowed_types and quest_type not in allowed_types:
            replacement = "exploration" if "exploration" in allowed_types else sorted(allowed_types)[0]
            self._record(
                changes,
                code="NORMALIZE_QUEST_TYPE",
                path="quest_type",
                before=quest.get("quest_type"),
                after=replacement,
                reason="The quest type must belong to the schema enumeration.",
            )
            quest["quest_type"] = replacement

    def _repair_core_references(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        rescue_targets = {
            self._clean_text(objective.get("target"))
            for objective in quest.get("objectives", [])
            if isinstance(objective, dict)
            and self._clean_text(objective.get("action")).lower() == "rescue"
        }

        giver = self._clean_text(quest.get("giver_npc"))
        giver_is_valid = self.world.get_entity_type(giver) == "npc"
        giver_is_rescue_target = giver in rescue_targets and bool(giver)

        if not giver_is_valid or giver_is_rescue_target:
            replacement = self._first_entity_id(
                "npc",
                exclude=rescue_targets,
            )
            if replacement:
                self._record(
                    changes,
                    code=(
                        "CHANGE_SELF_RESCUE_GIVER"
                        if giver_is_rescue_target
                        else "REPAIR_GIVER_NPC"
                    ),
                    path="giver_npc",
                    before=quest.get("giver_npc"),
                    after=replacement,
                    reason=(
                        "A rescued NPC cannot also be the quest giver."
                        if giver_is_rescue_target
                        else "giver_npc must reference an NPC in the world."
                    ),
                )
                quest["giver_npc"] = replacement

        location = self._clean_text(quest.get("start_location"))
        if self.world.get_entity_type(location) != "location":
            replacement = self._first_entity_id("location")
            if replacement:
                self._record(
                    changes,
                    code="REPAIR_START_LOCATION",
                    path="start_location",
                    before=quest.get("start_location"),
                    after=replacement,
                    reason="start_location must reference a location in the world.",
                )
                quest["start_location"] = replacement

    def _infer_action_for_target(self, target_id: str) -> str:
        target_type = self.world.get_entity_type(target_id)
        preferences = {
            "npc": "talk",
            "location": "travel",
            "item": "collect",
            "object": "inspect",
            "enemy": "defeat",
            "faction": "interact",
        }
        return preferences.get(target_type or "", "interact")

    def _target_for_action(self, action: str) -> Optional[str]:
        expected_types = DEFAULT_ACTION_TARGET_TYPES.get(action, set())
        for entity_type in sorted(expected_types):
            candidate = self._first_entity_id(entity_type)
            if candidate:
                return candidate
        return None

    def _condition_for_objective(self, action: str, target: str) -> str:
        templates = {
            "talk": f"O jogador conclui o diálogo com {target}.",
            "return": f"O jogador retorna com sucesso para {target}.",
            "collect": f"O inventário do jogador contém {target}.",
            "deliver": f"O jogador entrega o recurso solicitado para {target}.",
            "visit": f"O jogador alcança e visita {target}.",
            "travel": f"O jogador alcança a localização {target}.",
            "investigate": f"O jogador conclui a investigação relacionada a {target}.",
            "inspect": f"O jogador inspeciona completamente {target}.",
            "interact": f"O jogador conclui a interação com {target}.",
            "defeat": f"A entidade {target} foi derrotada pelo jogador.",
            "protect": f"O jogador protege {target} até o fim da etapa.",
            "rescue": f"A entidade {target} foi resgatada com sucesso.",
            "escort": f"O jogador escolta {target} até o destino definido.",
            "use": f"O jogador utiliza {target} na situação prevista.",
            "unlock": f"O jogador desbloqueia {target}.",
        }
        return templates.get(action, f"O jogador conclui a ação {action} sobre {target}.")

    def _make_support_objective(
        self,
        quest: Dict[str, Any],
        existing_actions: Set[str],
    ) -> Dict[str, Any]:
        giver = self._clean_text(quest.get("giver_npc"))
        location = self._clean_text(quest.get("start_location"))

        if "talk" not in existing_actions and self.world.get_entity_type(giver) == "npc":
            return {
                "step_id": "step_001",
                "depends_on": [],
                "action": "talk",
                "target": giver,
                "success_condition": self._condition_for_objective("talk", giver),
            }

        if "travel" not in existing_actions and self.world.get_entity_type(location) == "location":
            return {
                "step_id": "step_001",
                "depends_on": [],
                "action": "travel",
                "target": location,
                "success_condition": self._condition_for_objective("travel", location),
            }

        if self.world.get_entity_type(giver) == "npc":
            return {
                "step_id": "step_001",
                "depends_on": [],
                "action": "return",
                "target": giver,
                "success_condition": self._condition_for_objective("return", giver),
            }

        target = location or self._first_entity_id("location") or "unknown_target"
        return {
            "step_id": "step_001",
            "depends_on": [],
            "action": "travel",
            "target": target,
            "success_condition": self._condition_for_objective("travel", target),
        }

    def _repair_objectives(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before_objectives = copy.deepcopy(quest.get("objectives"))
        raw_objectives = quest.get("objectives", [])
        objectives = [
            copy.deepcopy(objective)
            for objective in raw_objectives
            if isinstance(objective, dict)
        ] if isinstance(raw_objectives, list) else []

        minimum = self._array_min_items("objectives", default=1)
        maximum = self._array_max_items("objectives")

        if maximum is not None and len(objectives) > maximum:
            objectives = objectives[:maximum]

        existing_actions = {
            self._clean_text(objective.get("action")).lower()
            for objective in objectives
        }

        while len(objectives) < minimum:
            support = self._make_support_objective(quest, existing_actions)
            # A support action should normally introduce the existing main task.
            objectives.insert(0, support)
            existing_actions.add(support["action"])

        allowed_actions = set(
            self._schema_property("objectives")
            .get("items", {})
            .get("properties", {})
            .get("action", {})
            .get("enum", [])
        )

        normalized: List[Dict[str, Any]] = []
        for index, objective in enumerate(objectives, start=1):
            target = self._clean_text(objective.get("target"))
            action = self._clean_text(objective.get("action")).lower()

            target_type = self.world.get_entity_type(target)
            expected_types = DEFAULT_ACTION_TARGET_TYPES.get(action, set())

            if action not in allowed_actions:
                action = self._infer_action_for_target(target)

            expected_types = DEFAULT_ACTION_TARGET_TYPES.get(action, set())
            if target_type is None or (expected_types and target_type not in expected_types):
                replacement_target = self._target_for_action(action)
                if replacement_target:
                    target = replacement_target
                elif target_type:
                    action = self._infer_action_for_target(target)
                else:
                    action = "travel"
                    target = (
                        self._clean_text(quest.get("start_location"))
                        or self._first_entity_id("location")
                        or "unknown_target"
                    )

            success = objective.get("success_condition")
            success_text = self._clean_text(success)
            if len(success_text) < 12:
                success_text = self._condition_for_objective(action, target)

            step_id = f"step_{index:03d}"
            depends_on = [] if index == 1 else [f"step_{index - 1:03d}"]

            normalized.append(
                {
                    "step_id": step_id,
                    "depends_on": depends_on,
                    "action": action,
                    "target": target,
                    "success_condition": success_text,
                }
            )

        quest["objectives"] = normalized
        self._record(
            changes,
            code="NORMALIZE_OBJECTIVES",
            path="objectives",
            before=before_objectives,
            after=normalized,
            reason=(
                "Objectives must satisfy schema cardinality and form a sequential acyclic dependency graph."
            ),
        )

    def _repair_preconditions(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before = copy.deepcopy(quest.get("preconditions"))
        raw = quest.get("preconditions", [])
        values = [
            self._clean_text(value)
            for value in raw
            if isinstance(value, str) and self._clean_text(value)
        ] if isinstance(raw, list) else []

        minimum = self._array_min_items("preconditions", default=0)
        while len(values) < minimum:
            values.append("O jogador ainda não concluiu esta quest.")

        quest["preconditions"] = values
        self._record(
            changes,
            code="NORMALIZE_PRECONDITIONS",
            path="preconditions",
            before=before,
            after=values,
            reason="Preconditions must follow the schema cardinality and string type.",
        )

    def _repair_completion_conditions(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before = copy.deepcopy(quest.get("completion_conditions"))
        raw = quest.get("completion_conditions", [])
        values = [
            self._clean_text(value)
            for value in raw
            if isinstance(value, str) and len(self._clean_text(value)) >= 12
        ] if isinstance(raw, list) else []

        objectives = quest.get("objectives", [])
        fallback = "A condição final da quest foi satisfeita pelo jogador."
        if isinstance(objectives, list) and objectives:
            final = objectives[-1]
            if isinstance(final, dict):
                fallback = self._clean_text(final.get("success_condition")) or fallback

        minimum = self._array_min_items("completion_conditions", default=1)
        while len(values) < minimum:
            values.append(fallback)

        quest["completion_conditions"] = values
        self._record(
            changes,
            code="NORMALIZE_COMPLETION_CONDITIONS",
            path="completion_conditions",
            before=before,
            after=values,
            reason="Completion conditions must be concrete strings and satisfy schema cardinality.",
        )

    def _repair_rewards(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before = copy.deepcopy(quest.get("rewards"))
        raw = quest.get("rewards", [])
        rewards: List[Dict[str, Any]] = []

        if isinstance(raw, list):
            for reward in raw:
                if not isinstance(reward, dict):
                    continue
                reward_type = self._clean_text(reward.get("type"))
                value = reward.get("value")
                if reward_type == "item":
                    if self.world.get_entity_type(self._clean_text(value)) != "item":
                        value = self._first_entity_id("item")
                    if value:
                        rewards.append({"type": "item", "value": value})
                elif reward_type in {"currency", "reputation"}:
                    if not isinstance(value, (int, float)):
                        value = 100
                    rewards.append({"type": reward_type, "value": value})
                elif reward_type == "unlock":
                    unlock_value = self._clean_text(value) or "quest_progression"
                    rewards.append({"type": "unlock", "value": unlock_value})

        minimum = self._array_min_items("rewards", default=1)
        while len(rewards) < minimum:
            rewards.append({"type": "currency", "value": 100})

        quest["rewards"] = rewards
        self._record(
            changes,
            code="NORMALIZE_REWARDS",
            path="rewards",
            before=before,
            after=rewards,
            reason="Rewards must match the schema and item rewards must reference world items.",
        )

    def _repair_tags(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before = copy.deepcopy(quest.get("reusable_tags"))
        raw = quest.get("reusable_tags", [])
        tags: List[str] = []

        if isinstance(raw, list):
            for value in raw:
                tag = self._slug(self._clean_text(value))
                if tag and tag not in tags:
                    tags.append(tag)

        candidates = [
            self._slug(self._clean_text(quest.get("quest_type"))),
            *[
                self._slug(self._clean_text(objective.get("action")))
                for objective in quest.get("objectives", [])
                if isinstance(objective, dict)
            ],
            "structured_quest",
            "world_grounded",
        ]

        minimum = self._array_min_items("reusable_tags", default=0)
        for candidate in candidates:
            if len(tags) >= minimum:
                break
            if candidate and candidate not in tags:
                tags.append(candidate)

        quest["reusable_tags"] = tags
        self._record(
            changes,
            code="NORMALIZE_TAGS",
            path="reusable_tags",
            before=before,
            after=tags,
            reason="Tags must be unique snake_case strings and satisfy schema cardinality.",
        )

    def _repair_design_notes(
        self,
        quest: Dict[str, Any],
        changes: List[RepairChange],
    ) -> None:
        before = copy.deepcopy(quest.get("design_notes"))
        raw = quest.get("design_notes")
        notes = copy.deepcopy(raw) if isinstance(raw, dict) else {}

        title = self._clean_text(quest.get("title")) or "a quest"
        defaults = {
            "intended_player_experience": (
                f"Permitir que o jogador avance de forma clara pelos objetivos de {title}."
            ),
            "reuse_potential": (
                "A estrutura pode ser reutilizada com outras entidades, locais e recompensas."
            ),
            "integration_notes": (
                "A integração requer rastreamento de objetivos, dependências e condições de conclusão."
            ),
        }

        for field_name, default_value in defaults.items():
            current = self._clean_text(notes.get(field_name))
            min_length = self._string_min_length(
                (
                    "properties",
                    "design_notes",
                    "properties",
                    field_name,
                ),
                default=12,
            )
            if len(current) < min_length:
                notes[field_name] = default_value
            else:
                notes[field_name] = current

        quest["design_notes"] = notes
        self._record(
            changes,
            code="NORMALIZE_DESIGN_NOTES",
            path="design_notes",
            before=before,
            after=notes,
            reason="Design notes cannot contain empty or underspecified fields.",
        )
