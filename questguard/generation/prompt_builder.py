from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from questguard.repositories.world_repository import WorldRepository


def build_generation_prompt(
    *,
    world: WorldRepository,
    schema: Dict[str, Any],
    number_of_quests: int,
    batch_index: int,
    forbidden_signatures: Iterable[str] = (),
) -> str:
    return f"""
You are generating structured quests for a small 2D RPG.
Treat each quest as an executable software artifact, not only as narrative text.

Return ONLY valid JSON with exactly one top-level key named \"quests\".
Generate exactly {number_of_quests} quests for batch {batch_index}.

MANDATORY RULES:
- All quest IDs must follow batch_{batch_index:02d}_quest_NNN.
- Use Portuguese for narrative fields and snake_case without accents for IDs.
- Every quest must comply with the supplied JSON Schema.
- giver_npc must use an NPC ID.
- start_location must use a location ID.
- objective targets must exist in the world and match the action.
- item rewards must use item IDs.
- Use 2 to 4 concrete objectives in every quest. Never generate only one objective.
- Restart local objective numbering in each quest: step_001, step_002, and so on.
- Every objective must have a unique step_id and a depends_on list.
- The first objective uses an empty depends_on list.
- Every later objective depends only on an earlier existing step.
- completion_conditions must contain concrete strings, never objects or booleans.
- reusable_tags must contain at least two distinct snake_case strings.
- Never return empty strings in design_notes or giver_npc.
- A rescued NPC cannot also be the quest giver.
- Avoid vague goals, hidden entities, implicit enemies, and generic completion conditions.
- Do not invent entities.
- Avoid repeated action/type structures listed under FORBIDDEN STRUCTURAL SIGNATURES.

WORLD ENTITY CATALOG:
{json.dumps(world.compact_catalog(), ensure_ascii=False, indent=2)}

FULL WORLD DATA:
{json.dumps(world.world, ensure_ascii=False, indent=2)}

QUEST JSON SCHEMA:
{json.dumps(schema, ensure_ascii=False, indent=2)}

FORBIDDEN STRUCTURAL SIGNATURES:
{json.dumps(list(forbidden_signatures), ensure_ascii=False, indent=2)}
""".strip()


def build_prompt_only_baseline(
    *,
    world: WorldRepository,
    number_of_quests: int,
    batch_index: int,
) -> str:
    return f"""
Generate exactly {number_of_quests} quests for a small 2D RPG.
Return only JSON using the top-level key \"quests\".
Use Portuguese text and unique quest IDs beginning with batch_{batch_index:02d}_quest_.
Each quest should contain a title, summary, type, giver, location, objectives,
preconditions, completion conditions, rewards, tags, and design notes.
Use the following world as inspiration and avoid inventing entities when possible:
{json.dumps(world.world, ensure_ascii=False, indent=2)}
""".strip()
