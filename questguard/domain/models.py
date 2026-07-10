from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    data: Dict[str, Any]


@dataclass(frozen=True)
class GeneratedBatch:
    batch_index: int
    quests: List[Dict[str, Any]]
    raw_response: str
    requested_count: int = 0
    generation_call_count: int = 1
    shortfall: int = 0
