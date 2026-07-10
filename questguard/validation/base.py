from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from questguard.domain.issues import ValidationReport


class QuestValidator(ABC):
    name: str

    @abstractmethod
    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        raise NotImplementedError
