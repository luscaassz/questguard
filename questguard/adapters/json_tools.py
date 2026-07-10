from __future__ import annotations

import json
import re
from typing import Any, Optional


def _clean_json_text(text: str) -> str:
    cleaned = text.strip().replace("\ufeff", "").replace("\u200b", "")
    cleaned = re.sub(r"^\s*```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def extract_json(text: str) -> Optional[Any]:
    """Extract the first complete JSON value from an LLM response.

    The function accepts pure JSON, fenced JSON and JSON embedded in a small
    amount of surrounding text. ``JSONDecoder.raw_decode`` is used so that a
    valid object can still be recovered when the model appends commentary.
    """

    if not text:
        return None

    cleaned = _clean_json_text(text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    for index, character in enumerate(cleaned):
        if character not in "[{\"-0123456789tfn":
            continue

        try:
            parsed, _ = decoder.raw_decode(cleaned[index:])
            return parsed
        except json.JSONDecodeError:
            continue

    return None
