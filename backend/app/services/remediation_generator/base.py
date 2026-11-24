from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

from app.models.enums import FindingCategory, RemediationRunStatus
from app.schemas.remediation import PracticeItemOutput


class RemediationInput(BaseModel):
    """
    Grounded input context provided to a remediation question generator.
    Strictly constrained to reviewed finding details and question context.
    """
    finding_id: int
    finding_category: FindingCategory
    concept_name: Optional[str] = None
    evidence_excerpt: Optional[str] = None
    rationale: str
    question_prompt: str
    rubric: Optional[str] = None
    expected_answer: Optional[str] = None
    topic_name: Optional[str] = None
    topic_description: Optional[str] = None

    model_config = ConfigDict(frozen=True)


class RemediationResult(BaseModel):
    """Result returned by a remediation generator."""
    status: RemediationRunStatus
    generator_name: str
    items: List[PracticeItemOutput] = []
    error_message: Optional[str] = None


class BaseRemediationGenerator(ABC):
    """Abstract interface for provider-independent remediation question generators."""

    @abstractmethod
    async def generate_practice(self, input_data: RemediationInput) -> RemediationResult:
        """
        Generates targeted practice items for a reviewed finding.
        Guarantees:
        - Never fabricates context when rubric/expected answer or prompt is absent.
        - Preserves separation of student-facing prompt from teacher answer key.
        - Supports documented formats (short_answer, multiple_choice, explain_reasoning).
        """
        pass
