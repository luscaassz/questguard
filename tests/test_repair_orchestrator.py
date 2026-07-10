from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from questguard.config import Settings
from questguard.domain.issues import combine_reports
from questguard.ports.llm import LLMClient
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
        raise AssertionError("The deterministic repair should solve this quest without an LLM call.")


def make_orchestrator(tmp_path: Path, schema: Dict[str, Any], world) -> RepairOrchestrator:
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
    return RepairOrchestrator(
        llm=FailIfCalledLLM(),
        settings=settings,
        world=world,
        schema=schema,
        validators=validators,
    )


def base_quest() -> Dict[str, Any]:
    return {
        "quest_id": "batch_01_quest_001",
        "title": "Obter o mapa",
        "summary": "Obter um mapa antigo para a Guilda dos Artesãos.",
        "quest_type": "collection",
        "giver_npc": "npc_explorador_cael",
        "start_location": "loc_floresta",
        "objectives": [
            {
                "step_id": "step_001",
                "depends_on": [],
                "action": "collect",
                "target": "item_mapa_antigo",
                "success_condition": "obter o mapa antigo",
            }
        ],
        "preconditions": [],
        "completion_conditions": [{"type": "bool", "value": True}],
        "rewards": [{"type": "item", "value": "item_mapa_antigo"}],
        "reusable_tags": ["coleta"],
        "design_notes": {
            "intended_player_experience": "Coletar um item importante.",
            "reuse_potential": "",
            "integration_notes": "",
        },
        "generation_batch": 1,
        "generation_index_in_batch": 1,
        "generation_global_index": 1,
        "generation_mode": "quality_gate_architecture",
        "generation_model": "llama3.2",
    }


def test_deterministic_repair_fixes_short_objective_list_and_condition_type(
    tmp_path, schema, world
):
    orchestrator = make_orchestrator(tmp_path, schema, world)
    result = orchestrator.repair(base_quest())

    assert result.repaired is True
    assert result.attempts == 0
    assert combine_reports(result.reports).passed is True
    assert len(result.final_quest["objectives"]) >= 2
    assert result.final_quest["objectives"][0]["step_id"] == "step_001"
    assert result.final_quest["objectives"][1]["depends_on"] == ["step_001"]
    assert all(
        isinstance(condition, str)
        for condition in result.final_quest["completion_conditions"]
    )
    assert result.deterministic_changes


def test_deterministic_repair_breaks_self_cycle_and_fills_giver(
    tmp_path, schema, world
):
    quest = base_quest()
    quest["quest_id"] = "batch_01_quest_003"
    quest["giver_npc"] = ""
    quest["quest_type"] = "combat"
    quest["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": ["step_001"],
            "action": "defeat",
            "target": "enemy_lobo_sombrio",
            "success_condition": "derrotar o lobo sombrio",
        }
    ]

    orchestrator = make_orchestrator(tmp_path, schema, world)
    result = orchestrator.repair(quest)

    assert combine_reports(result.reports).passed is True
    assert world.get_entity_type(result.final_quest["giver_npc"]) == "npc"
    objectives = result.final_quest["objectives"]
    assert objectives[0]["depends_on"] == []
    assert objectives[1]["depends_on"] == ["step_001"]


def test_deterministic_repair_changes_self_rescue_giver(tmp_path, schema, world):
    quest = base_quest()
    quest["quest_id"] = "batch_01_quest_002"
    quest["quest_type"] = "rescue"
    quest["giver_npc"] = "npc_curandeira_lia"
    quest["objectives"] = [
        {
            "step_id": "step_001",
            "depends_on": [],
            "action": "rescue",
            "target": "npc_curandeira_lia",
            "success_condition": "A curandeira Lia foi resgatada.",
        }
    ]

    orchestrator = make_orchestrator(tmp_path, schema, world)
    result = orchestrator.repair(quest)

    assert combine_reports(result.reports).passed is True
    assert result.final_quest["giver_npc"] != "npc_curandeira_lia"
