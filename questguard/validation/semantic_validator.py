from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from questguard.config import Settings
from questguard.domain.issues import Issue, ValidationReport
from questguard.ports.llm import LLMClient
from questguard.repositories.world_repository import WorldRepository
from questguard.validation.base import QuestValidator


CRITERIA = (
    "narrative_consistency",
    "gameplay_clarity",
    "integration_readiness",
    "reusability",
    "maintainability",
    "game_design_quality",
)

REQUIRED_MINIMUMS = {
    "narrative_consistency": 3,
    "gameplay_clarity": 3,
    "integration_readiness": 3,
    "maintainability": 3,
}

ALLOWED_ISSUE_CODES = {
    "IMPLICIT_ENTITY",
    "UNTRACKED_NARRATIVE_ENTITY",
    "NARRATIVE_CONTRADICTION",
    "QUEST_GIVER_STATE_CONTRADICTION",
    "SUMMARY_OBJECTIVE_MISMATCH",
    "UNCLEAR_OBJECTIVE",
    "UNCLEAR_ITEM_ACQUISITION",
    "UNMODELLED_COMBAT_DEPENDENCY",
    "LOW_REUSABILITY",
    "LOW_MAINTAINABILITY",
    "LOW_GAME_DESIGN_QUALITY",
}

# Subjective observations are preserved for human inspection, but they do not
# become blocking validation issues automatically.
ADVISORY_ISSUE_CODES = {
    "SUMMARY_OBJECTIVE_MISMATCH",
    "LOW_REUSABILITY",
    "LOW_MAINTAINABILITY",
    "LOW_GAME_DESIGN_QUALITY",
}

# Severity is controlled by the architecture, not by the LLM.
SEVERITY_POLICY = {
    "IMPLICIT_ENTITY": "error",
    "UNTRACKED_NARRATIVE_ENTITY": "error",
    "NARRATIVE_CONTRADICTION": "error",
    "QUEST_GIVER_STATE_CONTRADICTION": "error",
    "UNCLEAR_OBJECTIVE": "warning",
    "UNCLEAR_ITEM_ACQUISITION": "warning",
    "UNMODELLED_COMBAT_DEPENDENCY": "error",
}

CRITERION_SUPPORT_CODES = {
    "narrative_consistency": {
        "NARRATIVE_CONTRADICTION",
        "QUEST_GIVER_STATE_CONTRADICTION",
    },
    "gameplay_clarity": {
        "UNCLEAR_OBJECTIVE",
        "UNCLEAR_ITEM_ACQUISITION",
    },
    "integration_readiness": {
        "IMPLICIT_ENTITY",
        "UNTRACKED_NARRATIVE_ENTITY",
        "UNMODELLED_COMBAT_DEPENDENCY",
    },
    "maintainability": set(),
}

COMBAT_ACTIONS = {"defeat", "combat", "fight"}
UNAVAILABLE_STEMS = (
    "sequestrad",
    "desaparecid",
    "aprisionad",
    "capturad",
    "morto",
    "morta",
    "indisponivel",
    "indisponível",
)
GENERIC_SUCCESS_PATTERNS = (
    "completar o objetivo",
    "concluir o objetivo",
    "terminar a missao",
    "terminar a missão",
    "resolver o problema",
    "fazer isso",
)


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


class SemanticValidator(QuestValidator):
    name = "semantic_llm"

    def __init__(
        self,
        *,
        llm: LLMClient,
        settings: Settings,
        world: WorldRepository,
    ):
        self.llm = llm
        self.settings = settings
        self.world = world

    def _world_facts(self) -> List[Dict[str, Any]]:
        facts: List[Dict[str, Any]] = []

        for entity in sorted(self.world.entities(), key=lambda item: item.entity_id):
            fact: Dict[str, Any] = {
                "id": entity.entity_id,
                "type": entity.entity_type,
            }

            for key in ("name", "role", "location_id"):
                value = entity.data.get(key)
                if value is not None:
                    fact[key] = value

            facts.append(fact)

        return facts

    def _build_prompt(self, quest: Dict[str, Any]) -> str:
        blocking_codes = [
            "IMPLICIT_ENTITY",
            "UNTRACKED_NARRATIVE_ENTITY",
            "NARRATIVE_CONTRADICTION",
            "QUEST_GIVER_STATE_CONTRADICTION",
            "UNCLEAR_OBJECTIVE",
            "UNCLEAR_ITEM_ACQUISITION",
            "UNMODELLED_COMBAT_DEPENDENCY",
        ]

        return f"""
    You are the semantic quality gate for ONE structured game quest.

    Return exactly ONE compact JSON object.
    Do not use Markdown.
    Do not return text outside JSON.
    Do not return a JSON string containing another JSON object.
    Return at most 2 issues.

    SCOPE:
    - Structural validity, required fields, IDs, entity types,
    action-target compatibility and graph dependencies were already
    checked by deterministic validators.
    - Do not report schema problems.
    - Do not report missing IDs or location IDs.
    - Do not report problems based only on an NPC profession or role.
    - The summary does not need to mention the quest giver location.
    - Only report semantic problems supported by the quest fields.
    - If no blocking semantic problem exists, return "issues": [].

    Every issue MUST include structured evidence. Without evidence, do not report an issue.

    ALLOWED ISSUE CODES:
    {json.dumps(blocking_codes, ensure_ascii=False)}

    EVIDENCE RULES:
    - giver_is_rescue_target
    - giver_is_defeat_target
    - giver_unavailable_but_required
    - untracked_entity_id
    - combat_target_not_modelled
    - unclear_objective_at_index
    - unclear_item_acquisition_at_index

    OUTPUT RULES:
    - Each explanation must have at most 160 characters.
    - Each suggestion must have at most 160 characters.
    - short_review must have at most 240 characters.
    - Do not return LOW_REUSABILITY.
    - Do not return LOW_MAINTAINABILITY.
    - Do not return LOW_GAME_DESIGN_QUALITY.
    - Do not return subjective design observations.
    - Do not repeat WORLD FACTS or QUEST in the response.

    Return this structure:

    {{
    "semantic_scores": {{
        "narrative_consistency": 0,
        "gameplay_clarity": 0,
        "integration_readiness": 0,
        "reusability": 0,
        "maintainability": 0,
        "game_design_quality": 0
    }},
    "issues": [
        {{
        "code": "ONE_ALLOWED_CODE",
        "severity": "info | warning | error",
        "explanation": "short explanation",
        "suggestion": "short suggestion",
        "path": "quest.field",
        "evidence": {{
            "rule": "ONE_EVIDENCE_RULE",
            "entity_id": "",
            "objective_index": 0,
            "quest_paths": [],
            "observed_values": []
        }}
        }}
    ],
    "short_review": "short review"
    }}

    WORLD FACTS:
    {json.dumps(self._world_facts(), ensure_ascii=False)}

    QUEST:
    {json.dumps(quest, ensure_ascii=False)}
    """.strip()


    @staticmethod
    def _objectives(quest: Dict[str, Any]) -> List[Dict[str, Any]]:
        objectives = quest.get("objectives", [])
        if not isinstance(objectives, list):
            return []
        return [item for item in objectives if isinstance(item, dict)]

    @staticmethod
    def _evidence(raw_issue: Dict[str, Any]) -> Dict[str, Any]:
        evidence = raw_issue.get("evidence", {})
        return evidence if isinstance(evidence, dict) else {}

    @staticmethod
    def _objective_at(
        objectives: Sequence[Dict[str, Any]],
        evidence: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        index = evidence.get("objective_index")
        if not isinstance(index, int) or isinstance(index, bool):
            return None
        if index < 0 or index >= len(objectives):
            return None
        return objectives[index]

    def _supports_giver_contradiction(
        self,
        rule: str,
        evidence: Dict[str, Any],
        quest: Dict[str, Any],
        objectives: Sequence[Dict[str, Any]],
    ) -> bool:
        giver = str(quest.get("giver_npc", "")).strip()
        if not giver:
            return False

        if rule == "giver_is_rescue_target":
            return any(
                objective.get("action") == "rescue"
                and str(objective.get("target", "")).strip() == giver
                for objective in objectives
            )

        if rule == "giver_is_defeat_target":
            return any(
                objective.get("action") in COMBAT_ACTIONS
                and str(objective.get("target", "")).strip() == giver
                for objective in objectives
            )

        if rule == "giver_unavailable_but_required":
            entity_id = str(evidence.get("entity_id", "")).strip()
            if entity_id != giver:
                return False

            narrative = " ".join(
                [
                    _normalized_text(quest.get("title")),
                    _normalized_text(quest.get("summary")),
                    *[
                        _normalized_text(value)
                        for value in quest.get("preconditions", [])
                        if isinstance(value, str)
                    ],
                ]
            )
            unavailable = any(stem in narrative for stem in UNAVAILABLE_STEMS)
            giver_required = any(
                objective.get("action") in {"talk", "deliver", "return"}
                and str(objective.get("target", "")).strip() == giver
                for objective in objectives
            )
            return unavailable and giver_required

        return False

    def _adjudicate_issue(
        self,
        raw_issue: Dict[str, Any],
        quest: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Return (decision, reason): accepted, advisory, or discarded."""
        code = str(raw_issue.get("code", "")).strip().upper()

        if code not in ALLOWED_ISSUE_CODES:
            return "discarded", "unsupported_issue_code"

        evidence = self._evidence(raw_issue)
        rule = str(evidence.get("rule", "")).strip()

        if not rule:
            return "discarded", "missing_structured_evidence"

        if code in ADVISORY_ISSUE_CODES:
            return "advisory", "subjective_human_review"

        objectives = self._objectives(quest)

        if code in {
            "NARRATIVE_CONTRADICTION",
            "QUEST_GIVER_STATE_CONTRADICTION",
        }:
            if self._supports_giver_contradiction(
                rule,
                evidence,
                quest,
                objectives,
            ):
                return "accepted", "verified_against_quest_fields"
            return "discarded", "contradicted_by_quest_fields"

        if code in {"IMPLICIT_ENTITY", "UNTRACKED_NARRATIVE_ENTITY"}:
            if rule != "untracked_entity_id":
                return "discarded", "unsupported_evidence_rule"
            entity_id = str(evidence.get("entity_id", "")).strip()
            if not entity_id:
                return "discarded", "missing_entity_id_evidence"
            if self.world.has_entity(entity_id):
                return "discarded", "entity_exists_in_world"
            return "accepted", "entity_absent_from_world"

        if code == "UNMODELLED_COMBAT_DEPENDENCY":
            if rule != "combat_target_not_modelled":
                return "discarded", "unsupported_evidence_rule"
            objective = self._objective_at(objectives, evidence)
            if objective is None:
                return "discarded", "invalid_objective_index"
            if objective.get("action") not in COMBAT_ACTIONS:
                return "discarded", "objective_is_not_combat"
            target = str(objective.get("target", "")).strip()
            if self.world.get_entity_type(target) == "enemy":
                return "discarded", "combat_target_is_modelled_enemy"
            return "accepted", "combat_target_not_modelled"

        if code == "UNCLEAR_OBJECTIVE":
            if rule != "unclear_objective_at_index":
                return "discarded", "unsupported_evidence_rule"
            objective = self._objective_at(objectives, evidence)
            if objective is None:
                return "discarded", "invalid_objective_index"
            action = str(objective.get("action", "")).strip()
            target = str(objective.get("target", "")).strip()
            condition = _normalized_text(objective.get("success_condition"))
            objectively_unclear = (
                not action
                or not target
                or not condition
                or condition in GENERIC_SUCCESS_PATTERNS
            )
            if objectively_unclear:
                return "accepted", "objective_has_unverifiable_fields"
            return "discarded", "objective_is_concrete"

        if code == "UNCLEAR_ITEM_ACQUISITION":
            if rule != "unclear_item_acquisition_at_index":
                return "discarded", "unsupported_evidence_rule"
            objective = self._objective_at(objectives, evidence)
            if objective is None:
                return "discarded", "invalid_objective_index"
            if objective.get("action") != "collect":
                return "discarded", "objective_is_not_collection"
            target = str(objective.get("target", "")).strip()
            condition = _normalized_text(objective.get("success_condition"))
            if self.world.get_entity_type(target) != "item":
                return "accepted", "collection_target_is_not_item"
            if not condition or condition in GENERIC_SUCCESS_PATTERNS:
                return "accepted", "collection_condition_is_not_verifiable"
            return "discarded", "item_acquisition_is_concrete"

        return "discarded", "no_deterministic_adjudication_rule"

    @staticmethod
    def _has_expected_result_shape(result: Dict[str, Any]) -> bool:
        scores = result.get("semantic_scores")
        issues = result.get("issues")

        if not isinstance(scores, dict) or not isinstance(issues, list):
            return False

        for criterion in CRITERIA:
            value = scores.get(criterion)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False

        return True

    def _request_semantic_result(
        self,
        prompt: str,
    ) -> Tuple[Optional[Dict[str, Any]], int, List[str]]:
        errors: List[str] = []
        maximum_attempts = 3

        retry_instructions = [
            "",
            (
                "\n\nRETRY INSTRUCTION:\n"
                "Return only one JSON object. "
                "Do not return Markdown, arrays, wrappers or text outside JSON. "
                "Return issues as an array. "
                "If there is no blocking issue, return issues: []."
            ),
            (
                "\n\nFINAL RETRY INSTRUCTION:\n"
                "Return exactly this minimal JSON shape:\n"
                '{"semantic_scores":{'
                '"narrative_consistency":5,'
                '"gameplay_clarity":5,'
                '"integration_readiness":5,'
                '"reusability":5,'
                '"maintainability":5,'
                '"game_design_quality":5'
                '},"issues":[],"short_review":"Quest sem problema bloqueante."}'
            ),
        ]

        for attempt in range(1, maximum_attempts + 1):
            current_prompt = prompt + retry_instructions[attempt - 1]

            try:
                result = self.llm.generate_json(
                    current_prompt,
                    model=self.settings.review_model,
                    temperature=0.0,
                    top_p=self.settings.top_p,
                )

                if self._has_expected_result_shape(result):
                    return result, attempt, errors

                errors.append(
                    "A resposta JSON não possui semantic_scores numéricos "
                    "e issues em formato de lista."
                )

            except Exception as error:
                errors.append(
                    f"{type(error).__name__}: {error}"
                )

        return None, maximum_attempts, errors

    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        prompt = self._build_prompt(quest)
        result, llm_attempts, llm_errors = self._request_semantic_result(prompt)

        report = ValidationReport(validator=self.name)

        if result is None:
            report.issues.append(
                Issue(
                    code="SEMANTIC_VALIDATION_UNAVAILABLE",
                    severity="warning",
                    message=(
                        "A avaliação semântica não pôde ser concluída porque "
                        "o LLM não retornou o objeto JSON esperado."
                    ),
                    suggestion=(
                        "Executar novamente a avaliação semântica ou encaminhar "
                        "a quest para revisão humana."
                    ),
                    source=self.name,
                )
            )

            report.metadata.update(
                {
                    "semantic_validation_status": "unavailable",
                    "llm_attempts": llm_attempts,
                    "llm_errors": llm_errors,
                    "semantic_scores": None,
                    "overall_score": None,
                    "short_review": "",
                    "raw_issue_count": 0,
                    "accepted_llm_issue_count": 0,
                    "advisory_llm_issue_count": 0,
                    "discarded_llm_issue_count": 0,
                    "discarded_issue_rate": 0.0,
                    "advisory_llm_issues": [],
                    "discarded_llm_issues": [],
                }
            )

            return report

        report.metadata["semantic_validation_status"] = "completed"
        report.metadata["llm_attempts"] = llm_attempts
        report.metadata["llm_errors"] = llm_errors
        raw_scores = result.get("semantic_scores", {})
        scores: Dict[str, float] = {}

        for criterion in CRITERIA:
            value = raw_scores.get(criterion, 0)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                value = 0
            scores[criterion] = max(0.0, min(5.0, float(value)))

        discarded_issues: List[Dict[str, Any]] = []
        advisory_issues: List[Dict[str, Any]] = []
        accepted_codes: List[str] = []
        raw_issues = result.get("issues", [])
        if not isinstance(raw_issues, list):
            raw_issues = []

        for raw_issue in raw_issues:
            if not isinstance(raw_issue, dict):
                discarded_issues.append(
                    {
                        "reason": "issue_not_an_object",
                        "raw_issue": raw_issue,
                    }
                )
                continue

            decision, reason = self._adjudicate_issue(raw_issue, quest)
            code = str(raw_issue.get("code", "")).strip().upper()

            if decision == "discarded":
                discarded_issues.append(
                    {
                        "reason": reason,
                        "raw_issue": raw_issue,
                    }
                )
                continue

            if decision == "advisory":
                advisory_issues.append(
                    {
                        "reason": reason,
                        "raw_issue": raw_issue,
                    }
                )
                continue

            severity = SEVERITY_POLICY.get(code, "warning")
            accepted_codes.append(code)
            report.issues.append(
                Issue(
                    code=code,
                    severity=severity,  # type: ignore[arg-type]
                    message=str(raw_issue.get("explanation", "Problema semântico.")),
                    path=str(raw_issue.get("path", "")),
                    suggestion=str(raw_issue.get("suggestion", "")),
                    source=self.name,
                    metadata={
                        "evidence": self._evidence(raw_issue),
                        "adjudication": reason,
                    },
                )
            )

        # A low LLM score alone is not enough to reject an artifact. It must be
        # corroborated by at least one accepted evidence-backed issue.
        for criterion, minimum in REQUIRED_MINIMUMS.items():
            supporting_codes = CRITERION_SUPPORT_CODES.get(criterion, set())
            has_support = bool(set(accepted_codes) & supporting_codes)

            if scores[criterion] < minimum and has_support:
                report.issues.append(
                    Issue(
                        code=f"LOW_{criterion.upper()}",
                        severity="error",
                        message=(
                            f"O critério {criterion} recebeu {scores[criterion]:.1f}, "
                            f"abaixo do mínimo {minimum}, e há evidência semântica "
                            "corroborante."
                        ),
                        suggestion=(
                            "Reescrever a quest para remover a contradição ou "
                            "dependência semântica identificada."
                        ),
                        source=self.name,
                    )
                )

        raw_issue_count = len(raw_issues)
        discarded_count = len(discarded_issues)
        report.metadata.update(
            {
                "semantic_scores": scores,
                "overall_score": sum(scores.values()) / len(scores),
                "short_review": result.get("short_review", ""),
                "raw_issue_count": raw_issue_count,
                "accepted_llm_issue_count": len(accepted_codes),
                "advisory_llm_issue_count": len(advisory_issues),
                "discarded_llm_issue_count": discarded_count,
                "discarded_issue_rate": (
                    discarded_count / raw_issue_count
                    if raw_issue_count
                    else 0.0
                ),
                "advisory_llm_issues": advisory_issues,
                "discarded_llm_issues": discarded_issues,
            }
        )
        return report
