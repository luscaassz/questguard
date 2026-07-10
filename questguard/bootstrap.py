from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from questguard.adapters.ollama_client import OllamaClient
from questguard.config import Settings
from questguard.generation.service import QuestGenerationService
from questguard.repair.orchestrator import RepairOrchestrator
from questguard.repositories.world_repository import WorldRepository
from questguard.reports.io import load_json
from questguard.validation.base import QuestValidator
from questguard.validation.graph_validator import GraphValidator
from questguard.validation.content_validator import ContentRuleValidator
from questguard.validation.referential_validator import ReferentialValidator
from questguard.validation.schema_validator import SchemaValidator
from questguard.validation.semantic_validator import SemanticValidator


@dataclass
class Application:
    settings: Settings
    schema: Dict[str, Any]
    world: WorldRepository
    llm: OllamaClient
    deterministic_validators: List[QuestValidator]
    semantic_validator: SemanticValidator
    generation_service: QuestGenerationService
    repair_orchestrator: RepairOrchestrator


def build_application(project_root: Path, include_semantic_in_repair: bool = False) -> Application:
    settings = Settings.from_project_root(project_root)
    schema = load_json(settings.schema_path)
    world = WorldRepository.from_path(settings.world_path)
    llm = OllamaClient(settings.ollama_url, settings.request_timeout_seconds)

    deterministic: List[QuestValidator] = [
        SchemaValidator(schema),
        ReferentialValidator(world),
        GraphValidator(),
        ContentRuleValidator(),
    ]
    semantic = SemanticValidator(llm=llm, settings=settings, world=world)
    repair_validators = deterministic + ([semantic] if include_semantic_in_repair else [])

    generation = QuestGenerationService(
        llm=llm,
        settings=settings,
        world=world,
        schema=schema,
    )
    repair = RepairOrchestrator(
        llm=llm,
        settings=settings,
        world=world,
        schema=schema,
        validators=repair_validators,
    )
    return Application(
        settings=settings,
        schema=schema,
        world=world,
        llm=llm,
        deterministic_validators=deterministic,
        semantic_validator=semantic,
        generation_service=generation,
        repair_orchestrator=repair,
    )
