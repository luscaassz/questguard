from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from questguard.domain.models import Entity


CATEGORY_TO_TYPE = {
    "npcs": "npc",
    "locations": "location",
    "items": "item",
    "factions": "faction",
    "enemies": "enemy",
    "objects": "object",
}


class WorldRepository:
    def __init__(self, world: Dict[str, Any]):
        self.world = world
        self._entities: Dict[str, Entity] = {}
        self._load_entities()

    @classmethod
    def from_path(cls, path: Path) -> "WorldRepository":
        with path.open("r", encoding="utf-8") as file:
            return cls(json.load(file))

    def _load_entities(self) -> None:
        for category, entity_type in CATEGORY_TO_TYPE.items():
            for raw_entity in self.world.get(category, []):
                entity_id = raw_entity.get("id")
                if not isinstance(entity_id, str) or not entity_id.strip():
                    continue
                entity_id = entity_id.strip()
                if entity_id in self._entities:
                    raise ValueError(f"ID de entidade duplicado no mundo: {entity_id}")
                self._entities[entity_id] = Entity(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    data=raw_entity,
                )

    def has_entity(self, entity_id: str) -> bool:
        return entity_id.strip() in self._entities if isinstance(entity_id, str) else False

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        if not isinstance(entity_id, str):
            return None
        return self._entities.get(entity_id.strip())

    def get_entity_type(self, entity_id: str) -> Optional[str]:
        entity = self.get_entity(entity_id)
        return entity.entity_type if entity else None

    def ids(self, entity_type: Optional[str] = None) -> Set[str]:
        if entity_type is None:
            return set(self._entities)
        return {
            entity_id
            for entity_id, entity in self._entities.items()
            if entity.entity_type == entity_type
        }

    def entities(self, entity_type: Optional[str] = None) -> List[Entity]:
        if entity_type is None:
            return list(self._entities.values())
        return [entity for entity in self._entities.values() if entity.entity_type == entity_type]

    def compact_catalog(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for entity_type in sorted(set(CATEGORY_TO_TYPE.values())):
            values = sorted(self.ids(entity_type))
            if values:
                result[entity_type] = values
        return result

    def coverage(self, referenced_ids: Iterable[str]) -> float:
        available = len(self._entities)
        if available == 0:
            return 0.0
        referenced = {entity_id for entity_id in referenced_ids if entity_id in self._entities}
        return len(referenced) / available
