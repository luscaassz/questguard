from __future__ import annotations

from typing import Any, Dict, List

from questguard.adapters.json_tools import extract_json
from questguard.config import Settings
from questguard.domain.models import GeneratedBatch
from questguard.generation.prompt_builder import build_prompt_only_baseline
from questguard.ports.llm import LLMClient
from questguard.repositories.world_repository import WorldRepository


class BaselineGenerationService:
    """Prompt-only baseline intentionally lacking schema and explicit quality constraints."""

    def __init__(self, *, llm: LLMClient, settings: Settings, world: WorldRepository):
        self.llm = llm
        self.settings = settings
        self.world = world

    @staticmethod
    def _extract_quest_list(raw: str) -> List[Dict[str, Any]]:
        parsed = extract_json(raw)
        quests = parsed.get("quests") if isinstance(parsed, dict) else parsed

        if not isinstance(quests, list):
            return []

        return [quest for quest in quests if isinstance(quest, dict)]

    def generate_batch(
        self,
        *,
        batch_index: int,
        number_of_quests: int,
        forbidden_signatures=(),
    ) -> GeneratedBatch:
        if number_of_quests <= 0:
            raise ValueError("number_of_quests deve ser maior que zero.")

        collected: List[Dict[str, Any]] = []
        raw_responses: List[str] = []
        call_count = 0

        while (
            len(collected) < number_of_quests
            and call_count < self.settings.max_generation_attempts
        ):
            remaining = number_of_quests - len(collected)
            call_count += 1

            prompt = build_prompt_only_baseline(
                world=self.world,
                number_of_quests=remaining,
                batch_index=batch_index,
            )
            raw = self.llm.generate_text(
                prompt,
                model=self.settings.generation_model,
                temperature=self.settings.generation_temperature,
                top_p=self.settings.top_p,
                json_mode=True,
            )
            raw_responses.append(raw)
            returned_quests = self._extract_quest_list(raw)
            collected.extend(returned_quests[:remaining])

        shortfall = max(0, number_of_quests - len(collected))

        if shortfall:
            raise ValueError(
                "A baseline não completou o batch após "
                f"{call_count} chamada(s): retornou {len(collected)} quest(s), "
                f"mas eram esperadas {number_of_quests}."
            )

        normalized: List[Dict[str, Any]] = []

        for index, source_quest in enumerate(collected, start=1):
            quest = dict(source_quest)
            quest["quest_id"] = f"batch_{batch_index:02d}_quest_{index:03d}"
            quest["generation_batch"] = batch_index
            quest["generation_index_in_batch"] = index
            quest["generation_global_index"] = (
                (batch_index - 1) * number_of_quests + index
            )
            quest["generation_mode"] = "prompt_only"
            quest["generation_model"] = self.settings.generation_model
            normalized.append(quest)

        combined_raw = "\n\n".join(
            f"===== GENERATION CALL {index} =====\n{raw}"
            for index, raw in enumerate(raw_responses, start=1)
        )

        return GeneratedBatch(
            batch_index=batch_index,
            quests=normalized,
            raw_response=combined_raw,
            requested_count=number_of_quests,
            generation_call_count=call_count,
            shortfall=0,
        )
