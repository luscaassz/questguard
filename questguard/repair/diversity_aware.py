from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from questguard.analysis.diversity_metrics import referenced_entities, structural_signature
from questguard.repair.deterministic import DeterministicQuestRepairer, RepairChange
from questguard.repositories.world_repository import WorldRepository
from questguard.validation.referential_validator import DEFAULT_ACTION_TARGET_TYPES


TARGET_ACTION_PREFERENCES: Dict[str, Tuple[str, ...]] = {
    "npc": ("talk", "rescue", "escort", "protect", "interact", "return"),
    "location": ("visit", "travel", "investigate", "protect", "return"),
    "item": ("collect", "use", "inspect", "investigate", "interact"),
    "object": ("inspect", "interact", "use", "unlock", "investigate", "collect"),
    "enemy": ("defeat",),
    "faction": ("interact",),
}


ACTION_TARGET_REPAIR_PREFERENCES: Dict[Tuple[str, str], str] = {
    ("visit", "npc"): "talk",
    ("visit", "item"): "inspect",
    ("visit", "object"): "inspect",
    ("travel", "npc"): "talk",
    ("travel", "item"): "collect",
    ("travel", "object"): "inspect",
    ("collect", "npc"): "talk",
    ("collect", "location"): "investigate",
    ("defeat", "object"): "interact",
    ("defeat", "location"): "investigate",
}

QUEST_TYPE_ACTION_PREFERENCES: Dict[str, Tuple[str, ...]] = {
    "dialogue": ("talk", "interact", "return"),
    "collection": ("collect", "inspect", "investigate", "return"),
    "exploration": ("investigate", "visit", "travel", "inspect", "interact"),
    "combat": ("defeat", "protect", "travel"),
    "rescue": ("rescue", "escort", "travel", "talk"),
    "delivery": ("deliver", "collect", "return", "talk"),
}


@dataclass
class DiversityRepairState:
    """Mutable context shared while a quest set is repaired sequentially."""

    signature_counts: Counter[str] = field(default_factory=Counter)
    entity_usage_counts: Counter[str] = field(default_factory=Counter)
    action_type_counts: Counter[str] = field(default_factory=Counter)
    registered_quest_ids: Set[str] = field(default_factory=set)

    @classmethod
    def from_quests(
        cls,
        quests: Iterable[Dict[str, Any]],
        world: WorldRepository,
    ) -> "DiversityRepairState":
        state = cls()
        for quest in quests:
            state.register(quest, world)
        return state

    def register(self, quest: Dict[str, Any], world: WorldRepository) -> None:
        quest_id = str(quest.get("quest_id", "")).strip()
        if quest_id and quest_id in self.registered_quest_ids:
            return

        signature = structural_signature(quest, world)
        self.signature_counts[signature] += 1
        for component in signature.split(" -> ") if signature else []:
            self.action_type_counts[component] += 1
        for entity_id in referenced_entities(quest, world):
            self.entity_usage_counts[entity_id] += 1
        if quest_id:
            self.registered_quest_ids.add(quest_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_counts": dict(self.signature_counts),
            "entity_usage_counts": dict(self.entity_usage_counts),
            "action_type_counts": dict(self.action_type_counts),
            "registered_quest_count": len(self.registered_quest_ids),
        }


class DiversityAwareQuestRepairer(DeterministicQuestRepairer):
    """Repairs validity while minimizing structural homogenization.

    The C4 repairer optimizes primarily for validity. C5 adds a set-level
    context and follows four policies:

    1. preserve an existing valid target and change the action first;
    2. replace an entity only when it is absent or unusable;
    3. select the least-used compatible entity when replacement is required;
    4. penalize support objectives that recreate frequent signatures.
    """

    def __init__(
        self,
        *,
        world: WorldRepository,
        schema: Dict[str, Any],
        state: DiversityRepairState,
    ) -> None:
        super().__init__(world=world, schema=schema)
        self.state = state

    def _first_entity_id(
        self,
        entity_type: str,
        *,
        exclude: Optional[Set[str]] = None,
    ) -> Optional[str]:
        excluded = exclude or set()
        candidates = [
            entity_id
            for entity_id in self.world.ids(entity_type)
            if entity_id not in excluded
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda entity_id: (
                self.state.entity_usage_counts.get(entity_id, 0),
                entity_id,
            ),
        )

    def _compatible_actions(self, target_type: str) -> List[str]:
        allowed_actions = set(
            self._schema_property("objectives")
            .get("items", {})
            .get("properties", {})
            .get("action", {})
            .get("enum", [])
        )
        preferred = TARGET_ACTION_PREFERENCES.get(target_type, ())
        return [
            action
            for action in preferred
            if action in allowed_actions
            and target_type in DEFAULT_ACTION_TARGET_TYPES.get(action, set())
        ]

    def _choose_action_for_existing_target(
        self,
        *,
        target_type: str,
        quest_type: str,
        original_action: str,
    ) -> str:
        expected_types = DEFAULT_ACTION_TARGET_TYPES.get(original_action, set())
        if original_action and target_type in expected_types:
            return original_action

        direct_repair = ACTION_TARGET_REPAIR_PREFERENCES.get(
            (original_action, target_type)
        )
        if (
            direct_repair
            and target_type in DEFAULT_ACTION_TARGET_TYPES.get(direct_repair, set())
        ):
            return direct_repair

        candidates = self._compatible_actions(target_type)
        if not candidates:
            return self._infer_action_for_target("")

        quest_preferences = QUEST_TYPE_ACTION_PREFERENCES.get(quest_type, ())

        def score(action: str) -> Tuple[int, int, int, str]:
            component = f"{action}:{target_type}"
            semantic_rank = (
                quest_preferences.index(action)
                if action in quest_preferences
                else len(quest_preferences) + 1
            )
            original_penalty = 0 if action == original_action else 1
            frequency = self.state.action_type_counts.get(component, 0)
            return semantic_rank, frequency, original_penalty, action

        return min(candidates, key=score)

    def _least_used_target_for_action(self, action: str) -> Optional[str]:
        candidates: List[str] = []
        for entity_type in DEFAULT_ACTION_TARGET_TYPES.get(action, set()):
            candidates.extend(self.world.ids(entity_type))
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda entity_id: (
                self.state.entity_usage_counts.get(entity_id, 0),
                entity_id,
            ),
        )

    def _fallback_action_and_target(
        self,
        *,
        quest_type: str,
        quest: Dict[str, Any],
    ) -> Tuple[str, str]:
        preferred_actions = QUEST_TYPE_ACTION_PREFERENCES.get(
            quest_type,
            ("investigate", "travel", "talk"),
        )
        for action in preferred_actions:
            target = self._least_used_target_for_action(action)
            if target:
                return action, target

        location = self._clean_text(quest.get("start_location"))
        if self.world.get_entity_type(location) == "location":
            return "travel", location

        target = self._first_entity_id("location") or "unknown_target"
        return "travel", target

    def _normalize_objective_core(
        self,
        objective: Dict[str, Any],
        quest: Dict[str, Any],
    ) -> Dict[str, Any]:
        target = self._clean_text(objective.get("target"))
        action = self._clean_text(objective.get("action")).lower()
        quest_type = self._clean_text(quest.get("quest_type")).lower()
        target_type = self.world.get_entity_type(target)

        if target_type is not None:
            # Core C5 policy: preserve a grounded target and alter the action.
            action = self._choose_action_for_existing_target(
                target_type=target_type,
                quest_type=quest_type,
                original_action=action,
            )
        else:
            # The target cannot be preserved because it is not represented.
            if action not in DEFAULT_ACTION_TARGET_TYPES:
                action, target = self._fallback_action_and_target(
                    quest_type=quest_type,
                    quest=quest,
                )
            else:
                replacement = self._least_used_target_for_action(action)
                if replacement:
                    target = replacement
                else:
                    action, target = self._fallback_action_and_target(
                        quest_type=quest_type,
                        quest=quest,
                    )

        success_text = self._clean_text(objective.get("success_condition"))
        if len(success_text) < 12:
            success_text = self._condition_for_objective(action, target)

        return {
            "action": action,
            "target": target,
            "success_condition": success_text,
        }

    def _support_candidates(
        self,
        quest: Dict[str, Any],
        normalized_objectives: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        giver = self._clean_text(quest.get("giver_npc"))
        location = self._clean_text(quest.get("start_location"))

        def add(action: str, target: Optional[str]) -> None:
            if not target or self.world.get_entity_type(target) is None:
                return
            if any(
                item.get("action") == action and item.get("target") == target
                for item in normalized_objectives
            ):
                return
            candidates.append(
                {
                    "action": action,
                    "target": target,
                    "success_condition": self._condition_for_objective(action, target),
                }
            )

        add("talk", giver)
        add("travel", location)
        add("investigate", location)
        add("return", giver)
        add("inspect", self._first_entity_id("object"))
        add("collect", self._first_entity_id("item"))
        add("interact", self._first_entity_id("object"))

        if not candidates:
            action, target = self._fallback_action_and_target(
                quest_type=self._clean_text(quest.get("quest_type")).lower(),
                quest=quest,
            )
            add(action, target)
        return candidates

    def _candidate_signature(
        self,
        objectives: Sequence[Dict[str, Any]],
    ) -> str:
        parts: List[str] = []
        for objective in objectives:
            action = self._clean_text(objective.get("action")).lower() or "unknown"
            target = self._clean_text(objective.get("target"))
            target_type = self.world.get_entity_type(target) or "unknown"
            parts.append(f"{action}:{target_type}")
        return " -> ".join(parts)

    def _choose_support_objective(
        self,
        quest: Dict[str, Any],
        normalized_objectives: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        candidates = self._support_candidates(quest, normalized_objectives)
        if not candidates:
            action, target = self._fallback_action_and_target(
                quest_type=self._clean_text(quest.get("quest_type")).lower(),
                quest=quest,
            )
            return {
                "action": action,
                "target": target,
                "success_condition": self._condition_for_objective(action, target),
            }

        def score(candidate: Dict[str, Any]) -> Tuple[int, int, int, str, str]:
            candidate_sequence = [candidate, *normalized_objectives]
            signature = self._candidate_signature(candidate_sequence)
            entity_id = self._clean_text(candidate.get("target"))
            component = signature.split(" -> ", 1)[0]
            return (
                self.state.signature_counts.get(signature, 0),
                self.state.action_type_counts.get(component, 0),
                self.state.entity_usage_counts.get(entity_id, 0),
                self._clean_text(candidate.get("action")),
                entity_id,
            )

        return copy.deepcopy(min(candidates, key=score))

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

        maximum = self._array_max_items("objectives")
        if maximum is not None and len(objectives) > maximum:
            objectives = objectives[:maximum]

        normalized_core = [
            self._normalize_objective_core(objective, quest)
            for objective in objectives
        ]

        minimum = self._array_min_items("objectives", default=1)
        while len(normalized_core) < minimum:
            support = self._choose_support_objective(quest, normalized_core)
            normalized_core.insert(0, support)

        normalized: List[Dict[str, Any]] = []
        for index, objective in enumerate(normalized_core, start=1):
            normalized.append(
                {
                    "step_id": f"step_{index:03d}",
                    "depends_on": [] if index == 1 else [f"step_{index - 1:03d}"],
                    "action": objective["action"],
                    "target": objective["target"],
                    "success_condition": objective["success_condition"],
                }
            )

        quest["objectives"] = normalized
        self._record(
            changes,
            code="DIVERSITY_AWARE_OBJECTIVE_REPAIR",
            path="objectives",
            before=before_objectives,
            after=normalized,
            reason=(
                "Preserved grounded targets, selected compatible actions, and "
                "penalized repeated signatures and overused entities."
            ),
        )
