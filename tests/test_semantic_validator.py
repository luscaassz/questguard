from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from questguard.config import Settings
from questguard.ports.llm import LLMClient
from questguard.validation.semantic_validator import SemanticValidator


class StaticJSONLLM(LLMClient):
    def __init__(self, response: Dict[str, Any]):
        self.response = response
        self.last_prompt = ""

    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
        json_mode: bool = True,
    ) -> str:
        self.last_prompt = prompt
        return json.dumps(self.response, ensure_ascii=False)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path,
        output_dir=tmp_path,
        world_path=tmp_path / "world.json",
        schema_path=tmp_path / "quest_schema.json",
    )


def good_scores() -> Dict[str, int]:
    return {
        "narrative_consistency": 5,
        "gameplay_clarity": 5,
        "integration_readiness": 5,
        "reusability": 4,
        "maintainability": 5,
        "game_design_quality": 4,
    }


def test_discards_unsupported_missing_object_id_issue(tmp_path, world, valid_quest):
    llm = StaticJSONLLM(
        {
            "semantic_scores": good_scores(),
            "issues": [
                {
                    "code": "MISSING_OBJECT_ID",
                    "severity": "info",
                    "explanation": "O NPC não tem ID.",
                    "suggestion": "Adicionar ID.",
                    "path": "npcs/npc_explorador_cael",
                }
            ],
            "short_review": "Quest adequada.",
        }
    )

    validator = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    )
    report = validator.validate(valid_quest)

    assert report.passed is True
    assert report.issues == []
    assert report.metadata["discarded_llm_issue_count"] == 1
    assert (
        report.metadata["discarded_llm_issues"][0]["reason"]
        == "unsupported_issue_code"
    )


def test_discards_allowed_but_ungrounded_narrative_contradiction(
    tmp_path,
    world,
    valid_quest,
):
    llm = StaticJSONLLM(
        {
            "semantic_scores": good_scores(),
            "issues": [
                {
                    "code": "NARRATIVE_CONTRADICTION",
                    "severity": "info",
                    "explanation": "O papel do NPC não combina com a missão.",
                    "suggestion": "Trocar o NPC.",
                    "path": "quest.giver_npc",
                    "evidence": {
                        "rule": "giver_is_defeat_target",
                        "entity_id": "npc_explorador_cael",
                        "objective_index": 0,
                        "quest_paths": ["giver_npc", "objectives.0.target"],
                        "observed_values": [
                            "npc_explorador_cael",
                            "item_mapa_antigo",
                        ],
                    },
                }
            ],
            "short_review": "Suposta contradição.",
        }
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert report.issues == []
    assert report.metadata["discarded_llm_issue_count"] == 1
    assert (
        report.metadata["discarded_llm_issues"][0]["reason"]
        == "contradicted_by_quest_fields"
    )


def test_discards_semantic_issue_without_structured_evidence(
    tmp_path,
    world,
    valid_quest,
):
    llm = StaticJSONLLM(
        {
            "semantic_scores": good_scores(),
            "issues": [
                {
                    "code": "NARRATIVE_CONTRADICTION",
                    "severity": "info",
                    "explanation": "A profissão não combina com a missão.",
                    "suggestion": "Trocar o NPC.",
                    "path": "quest.giver_npc",
                }
            ],
            "short_review": "Suposta contradição.",
        }
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert report.issues == []
    assert report.metadata["discarded_llm_issue_count"] == 1
    assert (
        report.metadata["discarded_llm_issues"][0]["reason"]
        == "missing_structured_evidence"
    )


def test_accepts_verified_giver_rescue_contradiction(
    tmp_path,
    world,
    valid_quest,
):
    quest = deepcopy(valid_quest)
    quest["giver_npc"] = "npc_curandeira_lia"
    quest["objectives"][0] = {
        "step_id": "step_001",
        "depends_on": [],
        "action": "rescue",
        "target": "npc_curandeira_lia",
        "success_condition": "A curandeira Lia é resgatada.",
    }

    llm = StaticJSONLLM(
        {
            "semantic_scores": {
                **good_scores(),
                "narrative_consistency": 1,
            },
            "issues": [
                {
                    "code": "QUEST_GIVER_STATE_CONTRADICTION",
                    "severity": "info",
                    "explanation": "Lia oferece a missão para resgatar a si mesma.",
                    "suggestion": "Usar outro NPC como quest giver.",
                    "path": "giver_npc",
                    "evidence": {
                        "rule": "giver_is_rescue_target",
                        "entity_id": "npc_curandeira_lia",
                        "objective_index": 0,
                        "quest_paths": ["giver_npc", "objectives.0.target"],
                        "observed_values": [
                            "npc_curandeira_lia",
                            "npc_curandeira_lia",
                        ],
                    },
                }
            ],
            "short_review": "Há uma contradição verificável.",
        }
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(quest)

    assert report.passed is False
    codes = [issue.code for issue in report.issues]
    assert "QUEST_GIVER_STATE_CONTRADICTION" in codes
    assert "LOW_NARRATIVE_CONSISTENCY" in codes


def test_low_score_without_grounded_issue_does_not_reject(
    tmp_path,
    world,
    valid_quest,
):
    llm = StaticJSONLLM(
        {
            "semantic_scores": {
                "narrative_consistency": 0,
                "gameplay_clarity": 0,
                "integration_readiness": 0,
                "reusability": 0,
                "maintainability": 0,
                "game_design_quality": 0,
            },
            "issues": [],
            "short_review": "Notas baixas sem evidência.",
        }
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert report.issues == []


def test_subjective_issue_is_kept_as_advisory_metadata(
    tmp_path,
    world,
    valid_quest,
):
    llm = StaticJSONLLM(
        {
            "semantic_scores": good_scores(),
            "issues": [
                {
                    "code": "LOW_GAME_DESIGN_QUALITY",
                    "severity": "error",
                    "explanation": "A missão parece genérica.",
                    "suggestion": "Adicionar variedade.",
                    "path": "quest",
                    "evidence": {
                        "rule": "advisory_design_observation",
                        "entity_id": "",
                        "objective_index": 0,
                        "quest_paths": ["objectives"],
                        "observed_values": ["estrutura simples"],
                    },
                }
            ],
            "short_review": "Observação subjetiva.",
        }
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert report.issues == []
    assert report.metadata["advisory_llm_issue_count"] == 1


def test_prompt_requires_structured_evidence(tmp_path, world, valid_quest):
    llm = StaticJSONLLM(
        {
            "semantic_scores": good_scores(),
            "issues": [],
            "short_review": "Quest adequada.",
        }
    )

    validator = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    )
    validator.validate(valid_quest)

    assert "Every issue MUST include structured evidence" in llm.last_prompt
    assert "giver_is_rescue_target" in llm.last_prompt
    assert '"id": "npc_explorador_cael"' in llm.last_prompt


class SequenceTextLLM(LLMClient):
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.call_count = 0

    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
        json_mode: bool = True,
    ) -> str:
        response_index = min(self.call_count, len(self.responses) - 1)
        response = self.responses[response_index]
        self.call_count += 1
        return response


def test_generate_json_unwraps_single_object_array():
    llm = SequenceTextLLM(
        [
            json.dumps(
                [
                    {
                        "semantic_scores": good_scores(),
                        "issues": [],
                        "short_review": "Quest adequada.",
                    }
                ]
            )
        ]
    )

    result = llm.generate_json(
        "prompt",
        model="test",
        temperature=0,
        top_p=1,
    )

    assert result["issues"] == []


def test_semantic_validator_retries_after_malformed_json(
    tmp_path,
    world,
    valid_quest,
):
    llm = SequenceTextLLM(
        [
            "not valid json",
            json.dumps(
                {
                    "semantic_scores": good_scores(),
                    "issues": [],
                    "short_review": "Quest adequada.",
                },
                ensure_ascii=False,
            ),
        ]
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert report.metadata["semantic_validation_status"] == "completed"
    assert report.metadata["llm_attempts"] == 2
    assert len(report.metadata["llm_errors"]) == 1


def test_semantic_validator_reports_unavailable_without_crashing(
    tmp_path,
    world,
    valid_quest,
):
    llm = SequenceTextLLM(
        [
            "invalid",
            "still invalid",
            "also invalid",
        ]
    )

    report = SemanticValidator(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    ).validate(valid_quest)

    assert report.passed is True
    assert len(report.issues) == 1

    issue = report.issues[0]

    assert issue.code == "SEMANTIC_VALIDATION_UNAVAILABLE"
    assert issue.severity == "warning"

    assert (
        report.metadata["semantic_validation_status"]
        == "unavailable"
    )
    assert report.metadata["llm_attempts"] == 3
    assert len(report.metadata["llm_errors"]) == 3
    assert report.metadata["semantic_scores"] is None
    assert report.metadata["overall_score"] is None
