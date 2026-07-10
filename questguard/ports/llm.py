from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


def _remove_code_fences(text: str) -> str:
    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):]

    elif text.startswith("```"):
        text = text[len("```"):]

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


def _decode_json_value(text: str) -> Any:
    cleaned = _remove_code_fences(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    for index, character in enumerate(cleaned):
        if character not in "{[":
            continue

        try:
            value, _ = decoder.raw_decode(cleaned[index:])
            return value
        except json.JSONDecodeError:
            continue

    raise ValueError(
        "Não foi possível extrair JSON da resposta do LLM."
    )


def _extract_json_object(raw: str) -> dict[str, Any]:
    value: Any = _decode_json_value(raw)

    # Alguns modelos retornam um JSON contendo outra string JSON.
    for _ in range(3):
        if isinstance(value, dict):
            for wrapper in (
                "result",
                "review",
                "semantic_review",
                "response",
            ):
                wrapped = value.get(wrapper)

                if isinstance(wrapped, dict):
                    return wrapped

            return value

        if (
            isinstance(value, list)
            and len(value) == 1
            and isinstance(value[0], dict)
        ):
            return value[0]

        if isinstance(value, str):
            value = _decode_json_value(value)
            continue

        break

    raise ValueError(
        "A resposta do LLM não contém um objeto JSON. "
        f"Tipo extraído: {type(value).__name__}."
    )


class LLMClient(ABC):

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
        json_mode: bool = True,
    ) -> str:
        raise NotImplementedError

    def generate_json(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
    ) -> dict[str, Any]:
        raw = self.generate_text(
            prompt,
            model=model,
            temperature=temperature,
            top_p=top_p,
            json_mode=True,
        )

        return _extract_json_object(raw)