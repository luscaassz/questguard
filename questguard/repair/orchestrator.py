from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from questguard.adapters.json_tools import extract_json
from questguard.config import Settings
from questguard.domain.issues import ValidationReport, combine_reports
from questguard.ports.llm import LLMClient
from questguard.repair.deterministic import DeterministicQuestRepairer, RepairChange
from questguard.repositories.world_repository import WorldRepository
from questguard.validation.base import QuestValidator


@dataclass
class RepairResult:
    original_quest: Dict[str, Any]
    final_quest: Dict[str, Any]
    attempts: int
    repaired: bool
    reports: List[ValidationReport]
    raw_responses: List[str]
    deterministic_changes: List[Dict[str, Any]] = field(default_factory=list)


class RepairOrchestrator:
    def __init__(
        self,
        *,
        llm: LLMClient,
        settings: Settings,
        world: WorldRepository,
        schema: Dict[str, Any],
        validators: Sequence[QuestValidator],
        deterministic_repairer: DeterministicQuestRepairer | None = None,
    ):
        self.llm = llm
        self.settings = settings
        self.world = world
        self.schema = schema
        self.validators = list(validators)
        self.deterministic_repairer = deterministic_repairer or DeterministicQuestRepairer(
            world=world,
            schema=schema,
        )

    def _validate(self, quest: Dict[str, Any]) -> List[ValidationReport]:
        return [validator.validate(quest) for validator in self.validators]

    @staticmethod
    def _extract_quest_object(parsed: Any) -> Dict[str, Any] | None:
        if not isinstance(parsed, dict):
            return None

        if "quest_id" in parsed:
            return parsed

        wrapped = parsed.get("quest")
        if isinstance(wrapped, dict):
            return wrapped

        wrapped_list = parsed.get("quests")
        if (
            isinstance(wrapped_list, list)
            and len(wrapped_list) == 1
            and isinstance(wrapped_list[0], dict)
        ):
            return wrapped_list[0]

        return None

    def _prompt(
        self,
        quest: Dict[str, Any],
        reports: Sequence[ValidationReport],
        attempt: int,
    ) -> str:
        issues = [
            issue.to_dict()
            for report in reports
            for issue in report.issues
            if issue.severity in {"warning", "error"}
        ]

        return f"""
You are repairing ONE structured game quest.

Return ONLY the corrected quest object as valid JSON.
Do not use Markdown and do not return a wrapper named quest or quests.
This is repair attempt {attempt}.

NON-NEGOTIABLE RULES:
1. Preserve quest_id and all generation metadata exactly.
2. Correct every issue in ISSUES TO FIX.
3. Return between 2 and 4 objectives.
4. Number objectives locally as step_001, step_002, and so on.
5. The first objective must use an empty depends_on list.
6. Every later objective must depend only on an earlier existing step.
7. Never create self-dependencies or cycles.
8. Every objective must contain action, target and a concrete string success_condition.
9. giver_npc must reference an NPC from WORLD CATALOG.
10. start_location must reference a location from WORLD CATALOG.
11. All targets and item rewards must reference compatible entities from WORLD CATALOG.
12. completion_conditions must be an array of concrete strings, never objects or booleans.
13. reusable_tags must contain at least two distinct snake_case strings.
14. Never return empty strings.
15. A rescued NPC cannot also be the quest giver.
16. Do not invent narrative entities that are absent from the world.
17. Preserve information that is already valid.
18. The final object must comply with the complete JSON Schema.

WORLD CATALOG:
{json.dumps(self.world.compact_catalog(), ensure_ascii=False, indent=2)}

JSON SCHEMA:
{json.dumps(self.schema, ensure_ascii=False, indent=2)}

ISSUES TO FIX:
{json.dumps(issues, ensure_ascii=False, indent=2)}

CURRENT QUEST:
{json.dumps(quest, ensure_ascii=False, indent=2)}
""".strip()

    def _apply_deterministic_repair(
        self,
        quest: Dict[str, Any],
        collected_changes: List[RepairChange],
    ) -> Dict[str, Any]:
        repaired, changes = self.deterministic_repairer.repair(quest)
        collected_changes.extend(changes)
        return repaired

    def repair(self, quest: Dict[str, Any]) -> RepairResult:
        original = json.loads(json.dumps(quest))
        current = json.loads(json.dumps(quest))
        raw_responses: List[str] = []
        deterministic_changes: List[RepairChange] = []

        reports = self._validate(current)
        if combine_reports(reports).passed:
            return RepairResult(
                original_quest=original,
                final_quest=current,
                attempts=0,
                repaired=False,
                reports=reports,
                raw_responses=raw_responses,
                deterministic_changes=[],
            )

        preserved = {
            key: current.get(key)
            for key in (
                "quest_id",
                "generation_batch",
                "generation_index_in_batch",
                "generation_global_index",
                "generation_mode",
                "generation_model",
            )
            if key in current
        }

        # First quality-preserving strategy: deterministic normalization.
        current = self._apply_deterministic_repair(
            current,
            deterministic_changes,
        )
        current.update(preserved)
        reports = self._validate(current)

        if combine_reports(reports).passed:
            return RepairResult(
                original_quest=original,
                final_quest=current,
                attempts=0,
                repaired=True,
                reports=reports,
                raw_responses=raw_responses,
                deterministic_changes=[
                    change.to_dict() for change in deterministic_changes
                ],
            )

        # Creative/semantic fallback: LLM repair followed by deterministic cleanup.
        attempts_used = 0
        for attempt in range(1, self.settings.max_repair_attempts + 1):
            attempts_used = attempt
            raw = self.llm.generate_text(
                self._prompt(current, reports, attempt),
                model=self.settings.generation_model,
                temperature=0.1,
                top_p=self.settings.top_p,
                json_mode=True,
            )
            raw_responses.append(raw)

            parsed = extract_json(raw)
            repaired_quest = self._extract_quest_object(parsed)
            if repaired_quest is None:
                continue

            repaired_quest.update(preserved)
            current = self._apply_deterministic_repair(
                repaired_quest,
                deterministic_changes,
            )
            current.update(preserved)
            reports = self._validate(current)

            if combine_reports(reports).passed:
                return RepairResult(
                    original_quest=original,
                    final_quest=current,
                    attempts=attempt,
                    repaired=True,
                    reports=reports,
                    raw_responses=raw_responses,
                    deterministic_changes=[
                        change.to_dict() for change in deterministic_changes
                    ],
                )

        return RepairResult(
            original_quest=original,
            final_quest=current,
            attempts=attempts_used,
            repaired=False,
            reports=reports,
            raw_responses=raw_responses,
            deterministic_changes=[
                change.to_dict() for change in deterministic_changes
            ],
        )
