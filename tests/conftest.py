from __future__ import annotations

import json
from pathlib import Path

import pytest

from questguard.repositories.world_repository import WorldRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def schema():
    return json.loads((PROJECT_ROOT / "data" / "quest_schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def world():
    return WorldRepository.from_path(PROJECT_ROOT / "data" / "world.json")


@pytest.fixture
def valid_quest():
    return json.loads((PROJECT_ROOT / "data" / "example_valid_quest.json").read_text(encoding="utf-8"))
