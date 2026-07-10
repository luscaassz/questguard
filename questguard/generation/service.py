from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from questguard.adapters.json_tools import extract_json
from questguard.config import Settings
from questguard.domain.models import GeneratedBatch
from questguard.generation.prompt_builder import build_generation_prompt
from questguard.ports.llm import LLMClient
from questguard.repositories.world_repository import WorldRepository


class QuestGenerationService:
    def __init__(
        self,
        *,
        llm: LLMClient,
        settings: Settings,
        world: WorldRepository,
        schema: Dict[str, Any],
    ):
        self.llm = llm
        self.settings = settings
        self.world = world
        self.schema = schema

    @staticmethod
    def _looks_like_quest(value: Any) -> bool:
        """
        Verifica se um objeto JSON parece representar uma quest.

        Essa verificação evita confundir objetivos, recompensas e outros
        objetos internos com uma quest completa.
        """
        if not isinstance(value, dict):
            return False

        return (
            isinstance(value.get("title"), str)
            and isinstance(value.get("objectives"), list)
            and (
                isinstance(value.get("summary"), str)
                or isinstance(value.get("quest_type"), str)
            )
        )

    @classmethod
    def _recover_quests_from_truncated_json(
        cls,
        raw: str,
    ) -> List[Dict[str, Any]]:
        """
        Recupera quests completas de uma resposta parcialmente truncada.

        Por exemplo, se o modelo produzir quatro objetos de quest completos,
        mas não fechar corretamente a lista ou o objeto externo, o parser
        principal pode falhar. Este método tenta recuperar individualmente
        cada objeto completo.
        """
        decoder = json.JSONDecoder()
        recovered: List[Dict[str, Any]] = []
        seen_fingerprints: set[str] = set()

        for index, character in enumerate(raw):
            if character != "{":
                continue

            try:
                value, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue

            if not cls._looks_like_quest(value):
                continue

            # O ID é ignorado na assinatura porque será normalizado depois.
            fingerprint_source = dict(value)
            fingerprint_source.pop("quest_id", None)

            fingerprint = json.dumps(
                fingerprint_source,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

            if fingerprint in seen_fingerprints:
                continue

            recovered.append(value)
            seen_fingerprints.add(fingerprint)

        return recovered

    @classmethod
    def _extract_quest_list(
        cls,
        raw: str,
    ) -> List[Dict[str, Any]]:
        """
        Extrai a lista de quests da resposta do modelo.

        Primeiro tenta o parser JSON normal. Se a resposta estiver truncada
        ou malformada, tenta recuperar os objetos de quest completos.
        """
        parsed: Any = None

        try:
            parsed = extract_json(raw)
        except (ValueError, TypeError, json.JSONDecodeError):
            parsed = None

        if isinstance(parsed, dict):
            quests = parsed.get("quests")
        elif isinstance(parsed, list):
            quests = parsed
        else:
            quests = None

        if isinstance(quests, list):
            valid_quests = [
                quest
                for quest in quests
                if isinstance(quest, dict)
            ]

            if valid_quests:
                return valid_quests

        return cls._recover_quests_from_truncated_json(raw)

    def generate_batch(
        self,
        *,
        batch_index: int,
        number_of_quests: int,
        forbidden_signatures: Iterable[str] = (),
    ) -> GeneratedBatch:
        if number_of_quests <= 0:
            raise ValueError(
                "number_of_quests deve ser maior que zero."
            )

        collected: List[Dict[str, Any]] = []
        raw_responses: List[str] = []
        returned_counts: List[int] = []
        call_count = 0

        maximum_attempts = self.settings.max_generation_attempts

        while (
            len(collected) < number_of_quests
            and call_count < maximum_attempts
        ):
            remaining = number_of_quests - len(collected)
            call_count += 1

            prompt = build_generation_prompt(
                world=self.world,
                schema=self.schema,
                number_of_quests=remaining,
                batch_index=batch_index,
                forbidden_signatures=forbidden_signatures,
            )

            # Nas chamadas posteriores, reforça que o modelo deve produzir
            # apenas a quantidade de quests que ainda está faltando.
            if call_count > 1:
                prompt += f"""

CRITICAL BATCH COMPLETION RETRY:

The previous calls did not complete the requested batch.

Return exactly {remaining} new quest(s).

OUTPUT REQUIREMENTS:
- Return exactly one JSON object.
- The object must contain a "quests" array.
- The "quests" array must contain exactly {remaining} quest(s).
- Do not return Markdown.
- Do not return comments or explanations.
- Keep narrative text concise.
- Close every JSON object and array correctly.
""".strip()

            # A primeira chamada preserva a temperatura configurada.
            # As complementações usam temperatura zero para aumentar a
            # estabilidade estrutural da resposta.
            temperature = (
                self.settings.generation_temperature
                if call_count == 1
                else 0.0
            )

            raw = self.llm.generate_text(
                prompt,
                model=self.settings.generation_model,
                temperature=temperature,
                top_p=self.settings.top_p,
                json_mode=True,
            )

            raw_responses.append(raw)

            returned_quests = self._extract_quest_list(raw)
            returned_counts.append(len(returned_quests))

            # O modelo pode devolver mais quests do que o solicitado.
            # Somente a quantidade restante é incorporada.
            for quest in returned_quests:
                if len(collected) >= number_of_quests:
                    break

                collected.append(quest)

        shortfall = max(
            0,
            number_of_quests - len(collected),
        )

        if shortfall:
            raise ValueError(
                "O modelo não completou o batch após "
                f"{call_count} chamada(s): retornou "
                f"{len(collected)} quest(s), mas eram esperadas "
                f"{number_of_quests}. "
                f"Quests extraídas por chamada: {returned_counts}."
            )

        normalized: List[Dict[str, Any]] = []

        # Os IDs são atribuídos somente depois que todas as chamadas são
        # agregadas. Assim, IDs repetidos ou incorretos produzidos pelo
        # modelo não afetam o resultado final.
        for index, source_quest in enumerate(
            collected,
            start=1,
        ):
            quest = dict(source_quest)

            quest["quest_id"] = (
                f"batch_{batch_index:02d}_quest_{index:03d}"
            )
            quest["generation_batch"] = batch_index
            quest["generation_index_in_batch"] = index
            quest["generation_global_index"] = (
                (batch_index - 1) * number_of_quests
                + index
            )
            quest["generation_mode"] = (
                "quality_gate_architecture"
            )
            quest["generation_model"] = (
                self.settings.generation_model
            )

            normalized.append(quest)

        combined_raw = "\n\n".join(
            f"===== GENERATION CALL {index} =====\n{raw}"
            for index, raw in enumerate(
                raw_responses,
                start=1,
            )
        )

        return GeneratedBatch(
            batch_index=batch_index,
            quests=normalized,
            raw_response=combined_raw,
            requested_count=number_of_quests,
            generation_call_count=call_count,
            shortfall=0,
        )