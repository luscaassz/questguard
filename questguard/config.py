from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    output_dir: Path
    world_path: Path
    schema_path: Path
    ollama_url: str = "http://localhost:11434/api/generate"
    generation_model: str = "llama3.2"
    review_model: str = "llama3.2"
    generation_temperature: float = 0.7
    review_temperature: float = 0.1
    top_p: float = 0.9
    request_timeout_seconds: int = 360
    max_repair_attempts: int = 3
    max_generation_attempts: int = 8

    @classmethod
    def from_project_root(cls, project_root: Path) -> "Settings":
        project_root = project_root.resolve()
        data_dir = project_root / "data"
        output_dir = project_root / "outputs"
        return cls(
            base_dir=project_root,
            data_dir=data_dir,
            output_dir=output_dir,
            world_path=data_dir / "world.json",
            schema_path=data_dir / "quest_schema.json",
        )
