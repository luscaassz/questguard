from __future__ import annotations

import json
from pathlib import Path
from typing import List

from questguard.config import Settings
from questguard.generation.baseline_service import BaselineGenerationService
from questguard.generation.service import QuestGenerationService
from questguard.ports.llm import LLMClient


class SequenceLLM(LLMClient):
    def __init__(self, responses: List[str]):
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
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        base_dir=tmp_path,
        data_dir=tmp_path,
        output_dir=tmp_path,
        world_path=tmp_path / "world.json",
        schema_path=tmp_path / "quest_schema.json",
        max_generation_attempts=3,
    )


def response_with_count(count: int) -> str:
    return json.dumps(
        {"quests": [{"title": f"Quest {index}"} for index in range(count)]},
        ensure_ascii=False,
    )


def test_schema_guided_generation_completes_partial_batch(
    tmp_path,
    schema,
    world,
):
    llm = SequenceLLM(
        [response_with_count(4), response_with_count(1)]
    )
    service = QuestGenerationService(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
        schema=schema,
    )

    batch = service.generate_batch(
        batch_index=1,
        number_of_quests=5,
    )

    assert len(batch.quests) == 5
    assert batch.generation_call_count == 2
    assert batch.shortfall == 0
    assert [quest["quest_id"] for quest in batch.quests] == [
        "batch_01_quest_001",
        "batch_01_quest_002",
        "batch_01_quest_003",
        "batch_01_quest_004",
        "batch_01_quest_005",
    ]


def test_baseline_generation_completes_partial_batch(
    tmp_path,
    world,
):
    llm = SequenceLLM(
        [response_with_count(3), response_with_count(2)]
    )
    service = BaselineGenerationService(
        llm=llm,
        settings=make_settings(tmp_path),
        world=world,
    )

    batch = service.generate_batch(
        batch_index=2,
        number_of_quests=5,
    )

    assert len(batch.quests) == 5
    assert batch.generation_call_count == 2
    assert batch.quests[0]["quest_id"] == "batch_02_quest_001"
    assert batch.quests[-1]["quest_id"] == "batch_02_quest_005"
