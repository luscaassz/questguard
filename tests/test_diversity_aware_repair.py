from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from questguard.analysis.diversity_metrics import structural_signature
from questguard.config import Settings
from questguard.domain.issues import combine_reports
from questguard.ports.llm import LLMClient
from questguard.repair.diversity_aware import (
    DiversityAwareQuestRepairer,
    DiversityRepairState,
)
from questguard.repair.orchestrator import RepairOrchestrator
from questguard.validation.content_validator import ContentRuleValidator
from questguard.validation.graph_validator import GraphValidator
from questguard.validation.referential_validator import ReferentialValidator
from questguard.validation.schema_validator import SchemaValidator


class FailIfCalledLLM(LLMClient):
    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
        json_mode: bool = True,
    ) -> str:
        raise AssertionError("C5 deterministic repair should solve this case.")


def make_c5_orchestrator(
    tmp_path: Path,
    schema: Dict[str, Any],
    world,
    state: DiversityRepairState,
) -> RepairOrchestrator:
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path,
        output_dir=tmp_path,
        world_path=tmp_path / "world.json",
        schema_path=tmp_path / "quest_schema.json",
    )
    validators = [
        SchemaValidator(schema),
        ReferentialValidator(world),
        GraphValidator(),
        ContentRuleValidator(),
    ]
    repairer = DiversityAwareQuestRepairer(
        world=world,
        schema=schema,
        state=state,
    )
    return RepairOrchestrator(
        llm=FailIfCalledLLM(),
        settings=settings,
        world=world,
        schema=schema,
        validators=validators,
        deterministic_repairer=repairer,
    )


def test_c5_preserves_grounded_object_and_changes_incompatible_action(
    tmp_path, schema, world, valid_quest
):
    quest = copy.deepcopy(valid_quest)
    quest["quest_id"] = "batch_01_quest_010"
    quest["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "travel",
            "target": "loc_ruinas",
            "success_condition": "O jogador alcança as ruínas antigas.",
        },
        {
            "step_id": "step_002",
            "depends_on": ["step_001"],
            "action": "visit",
            "target": "object_bau_selado",
            "success_condition": "O jogador examina o baú selado nas ruínas.",
        },
    ]

    state = DiversityRepairState()
    orchestrator = make_c5_orchestrator(tmp_path, schema, world, state)
    result = orchestrator.repair(quest)

    assert combine_reports(result.reports).passed is True
    second = result.final_quest["objectives"][1]
    assert second["target"] == "object_bau_selado"
    assert second["action"] == "inspect"


def test_c5_uses_less_frequent_entities_when_replacement_is_required(
    tmp_path, schema, world, valid_quest
):
    frequent = copy.deepcopy(valid_quest)
    frequent["giver_npc"] = "npc_explorador_cael"
    frequent["start_location"] = "loc_floresta"
    frequent["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "travel",
            "target": "loc_floresta",
            "success_condition": "O jogador alcança a floresta nebulosa.",
        },
        {
            "step_id": "step_002",
            "depends_on": ["step_001"],
            "action": "talk",
            "target": "npc_explorador_cael",
            "success_condition": "O jogador conversa com Cael na floresta.",
        },
    ]
    state = DiversityRepairState.from_quests([frequent, frequent], world)

    quest = copy.deepcopy(valid_quest)
    quest["quest_id"] = "batch_01_quest_011"
    quest["giver_npc"] = "npc_inexistente"
    quest["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "visit",
            "target": "loc_inexistente",
            "success_condition": "O jogador visita uma localização válida do mundo.",
        },
        {
            "step_id": "step_002",
            "depends_on": ["step_001"],
            "action": "collect",
            "target": "item_mapa_antigo",
            "success_condition": "O jogador coleta o mapa antigo.",
        },
    ]

    orchestrator = make_c5_orchestrator(tmp_path, schema, world, state)
    result = orchestrator.repair(quest)

    assert combine_reports(result.reports).passed is True
    assert result.final_quest["giver_npc"] != "npc_explorador_cael"
    assert result.final_quest["objectives"][0]["target"] != "loc_floresta"


def test_c5_penalizes_an_already_used_structural_signature(
    tmp_path, schema, world, valid_quest
):
    repeated = copy.deepcopy(valid_quest)
    repeated["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "talk",
            "target": "npc_ferreiro_bran",
            "success_condition": "O jogador conversa com Bran sobre a tarefa.",
        },
        {
            "step_id": "step_002",
            "depends_on": ["step_001"],
            "action": "collect",
            "target": "item_mapa_antigo",
            "success_condition": "O jogador coleta o mapa antigo solicitado.",
        },
    ]
    repeated_signature = structural_signature(repeated, world)
    state = DiversityRepairState.from_quests([repeated, repeated], world)

    quest = copy.deepcopy(valid_quest)
    quest["quest_id"] = "batch_01_quest_012"
    quest["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "collect",
            "target": "item_erva_lunar",
            "success_condition": "O jogador coleta uma unidade de erva lunar.",
        }
    ]

    orchestrator = make_c5_orchestrator(tmp_path, schema, world, state)
    result = orchestrator.repair(quest)

    assert combine_reports(result.reports).passed is True
    assert structural_signature(result.final_quest, world) != repeated_signature
