from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Literal

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class Issue:
    code: str
    severity: Severity
    message: str
    path: str = ""
    suggestion: str = ""
    source: str = "deterministic"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationReport:
    validator: str
    issues: List[Issue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    def extend(self, issues: Iterable[Issue]) -> None:
        self.issues.extend(issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validator": self.validator,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata,
        }


def combine_reports(reports: Iterable[ValidationReport]) -> ValidationReport:
    reports = list(reports)
    combined = ValidationReport(validator="combined")
    combined.metadata["validators"] = [report.validator for report in reports]
    for report in reports:
        combined.extend(report.issues)
    return combined
