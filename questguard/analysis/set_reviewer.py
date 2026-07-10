from __future__ import annotations

import json
from typing import Any, Dict, List

from questguard.analysis.diversity_metrics import compute_set_metrics
from questguard.config import Settings
from questguard.ports.llm import LLMClient
from questguard.repositories.world_repository import WorldRepository


class SetReviewer:
    def __init__(self, *, llm: LLMClient, settings: Settings, world: WorldRepository):
        self.llm = llm
        self.settings = settings
        self.world = world

    def review(self, quests: List[Dict[str, Any]]) -> Dict[str, Any]:
        deterministic = compute_set_metrics(quests, self.world)
        compact = []
        for quest in quests:
            compact.append({
                "quest_id": quest.get("quest_id"),
                "quest_type": quest.get("quest_type"),
                "giver_npc": quest.get("giver_npc"),
                "start_location": quest.get("start_location"),
                "objectives": quest.get("objectives", []),
                "tags": quest.get("reusable_tags", []),
            })
        prompt = f"""
Review this complete quest set as a software-engineering and game-design artifact.
Use the deterministic metrics as evidence. Return ONLY valid JSON in Portuguese.
Score diversity, entity_coverage, design_balance, maintainability, and scalability from 0 to 5.
Identify duplicate quest IDs, overused entities, repeated patterns, strengths, weaknesses,
and actionable recommendations.

Return:
{{
  "set_scores": {{
    "diversity": 0,
    "entity_coverage": 0,
    "design_balance": 0,
    "maintainability": 0,
    "scalability": 0
  }},
  "duplicated_or_similar_quests": [],
  "overused_entities": [],
  "overused_patterns": [],
  "strengths": [],
  "weaknesses": [],
  "recommendations": [],
  "short_review": ""
}}

DETERMINISTIC METRICS:
{json.dumps(deterministic, ensure_ascii=False, indent=2)}

QUEST SET:
{json.dumps(compact, ensure_ascii=False, indent=2)}
""".strip()
        result = self.llm.generate_json(
            prompt,
            model=self.settings.review_model,
            temperature=self.settings.review_temperature,
            top_p=self.settings.top_p,
        )
        result["deterministic_metrics"] = deterministic
        scores = result.get("set_scores", {})
        values = [float(value) for value in scores.values() if isinstance(value, (int, float))]
        result["overall_set_score"] = sum(values) / len(values) if values else 0.0
        return result
