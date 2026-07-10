from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    fault_type: str
    quest: Dict[str, Any]
    expected_codes: List[str]


def _remove_required_field(quest: Dict[str, Any]) -> Dict[str, Any]:
    quest.pop("title", None)
    return quest


def _unknown_target(quest: Dict[str, Any]) -> Dict[str, Any]:
    quest["objectives"][0]["target"] = "entity_not_in_world"
    return quest


def _wrong_giver_type(quest: Dict[str, Any]) -> Dict[str, Any]:
    quest["giver_npc"] = "item_mapa_antigo"
    return quest


def _duplicate_step_id(quest: Dict[str, Any]) -> Dict[str, Any]:
    if len(quest.get("objectives", [])) >= 2:
        quest["objectives"][1]["step_id"] = quest["objectives"][0]["step_id"]
    return quest


def _missing_dependency(quest: Dict[str, Any]) -> Dict[str, Any]:
    quest["objectives"][0]["depends_on"] = ["step_inexistente"]
    return quest


def _cycle(quest: Dict[str, Any]) -> Dict[str, Any]:
    objectives = quest.get("objectives", [])
    if len(objectives) >= 2:
        first = objectives[0]["step_id"]
        second = objectives[1]["step_id"]
        objectives[0]["depends_on"] = [second]
        objectives[1]["depends_on"] = [first]
    return quest


def _generic_completion(quest: Dict[str, Any]) -> Dict[str, Any]:
    quest["completion_conditions"] = ["O jogador completa todos os objetivos da quest."]
    return quest


MUTATIONS: List[tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]], List[str]]] = [
    ("missing_required_field", _remove_required_field, ["SCHEMA_VIOLATION"]),
    ("unknown_target", _unknown_target, ["INVALID_OR_IMPLICIT_TARGET"]),
    ("wrong_giver_type", _wrong_giver_type, ["INVALID_QUEST_GIVER_TYPE"]),
    ("duplicate_step_id", _duplicate_step_id, ["DUPLICATE_STEP_ID"]),
    ("missing_dependency", _missing_dependency, ["MISSING_STEP_DEPENDENCY"]),
    ("cyclic_dependency", _cycle, ["CYCLIC_OBJECTIVE_DEPENDENCY"]),
    ("generic_completion", _generic_completion, ["GENERIC_COMPLETION_CONDITION"]),
]


def inject_faults(valid_quests: List[Dict[str, Any]]) -> List[Mutant]:
    mutants: List[Mutant] = []
    for quest_index, quest in enumerate(valid_quests, start=1):
        for fault_type, mutation, expected_codes in MUTATIONS:
            mutated = mutation(copy.deepcopy(quest))
            mutant_id = f"{quest.get('quest_id', quest_index)}::{fault_type}"
            mutated["mutation_id"] = mutant_id
            mutants.append(Mutant(mutant_id, fault_type, mutated, expected_codes))
    return mutants
