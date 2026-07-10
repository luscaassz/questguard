from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from questguard.analysis.diversity_metrics import compute_set_metrics, structural_signature
from questguard.analysis.graph_metrics import compute_graph_metrics
from questguard.domain.issues import ValidationReport, combine_reports
from questguard.generation.service import QuestGenerationService
from questguard.repair.orchestrator import RepairOrchestrator
from questguard.repositories.world_repository import WorldRepository
from questguard.validation.base import QuestValidator


@dataclass
class QuestPipelineResult:
    generated: List[Dict[str, Any]]
    accepted: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    validation_records: List[Dict[str, Any]]
    repair_records: List[Dict[str, Any]]
    graph_metrics: List[Dict[str, Any]]
    set_metrics: Dict[str, Any]


class QuestPipeline:
    def __init__(
        self,
        *,
        world: WorldRepository,
        generation_service: QuestGenerationService,
        validators: Sequence[QuestValidator],
        repair_orchestrator: RepairOrchestrator | None = None,
    ):
        self.world = world
        self.generation_service = generation_service
        self.validators = list(validators)
        self.repair_orchestrator = repair_orchestrator

    def _validate(self, quest: Dict[str, Any]) -> List[ValidationReport]:
        return [validator.validate(quest) for validator in self.validators]

    def run(self, *, batches: int, quests_per_batch: int, repair: bool) -> QuestPipelineResult:
        generated: List[Dict[str, Any]] = []
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        validation_records: List[Dict[str, Any]] = []
        repair_records: List[Dict[str, Any]] = []
        forbidden_signatures: List[str] = []

        for batch_index in range(1, batches + 1):
            batch = self.generation_service.generate_batch(
                batch_index=batch_index,
                number_of_quests=quests_per_batch,
                forbidden_signatures=forbidden_signatures,
            )
            generated.extend(batch.quests)

            for quest in batch.quests:
                reports = self._validate(quest)
                combined = combine_reports(reports)
                validation_records.append(
                    {
                        "quest_id": quest.get("quest_id"),
                        "stage": "initial",
                        "passed": combined.passed,
                        "reports": [report.to_dict() for report in reports],
                    }
                )

                final_quest = quest
                if not combined.passed and repair and self.repair_orchestrator:
                    repair_result = self.repair_orchestrator.repair(quest)
                    final_quest = repair_result.final_quest
                    final_combined = combine_reports(repair_result.reports)
                    repair_records.append(
                        {
                            "quest_id": quest.get("quest_id"),
                            "attempts": repair_result.attempts,
                            "repaired": repair_result.repaired,
                            "passed_after_repair": final_combined.passed,
                            "reports": [report.to_dict() for report in repair_result.reports],
                        }
                    )
                    combined = final_combined

                if combined.passed:
                    accepted.append(final_quest)
                    signature = structural_signature(final_quest, self.world)
                    if signature:
                        forbidden_signatures.append(signature)
                else:
                    rejected.append(final_quest)

        metrics = [compute_graph_metrics(quest, self.world) for quest in accepted]
        return QuestPipelineResult(
            generated=generated,
            accepted=accepted,
            rejected=rejected,
            validation_records=validation_records,
            repair_records=repair_records,
            graph_metrics=metrics,
            set_metrics=compute_set_metrics(accepted, self.world),
        )
