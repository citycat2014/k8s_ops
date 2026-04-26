"""Base analyzer class."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AnalysisResult:
    """Result from an analyzer."""
    pattern_id: str | None = None
    title: str = ""
    explanation: str = ""
    confidence: float = 0.0
    suggested_actions: list[str] = None

    def __post_init__(self):
        if self.suggested_actions is None:
            self.suggested_actions = []


class BaseAnalyzer(ABC):
    @abstractmethod
    def analyze(self, data: dict) -> AnalysisResult:
        ...
