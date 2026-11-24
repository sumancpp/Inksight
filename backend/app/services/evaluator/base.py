from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

from app.schemas.evaluation import FindingOutput
from app.schemas.follow_up import FollowUpGenerationInput, FollowUpQuestionPayload


class EvaluatorError(Exception):
    """Raised when an evaluator encounters an execution error."""
    def __init__(self, message: str, error_code: str = "EVALUATOR_EXECUTION_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class EvaluationInput(BaseModel):
    question_prompt: str
    expected_answer: Optional[str] = None
    rubric: Optional[str] = None
    topic_name: Optional[str] = None
    student_answer: str
    marks: float = 1.0
    question_type: Optional[str] = None
    difficulty: Optional[str] = "Medium"


class EvaluationResult(BaseModel):
    evaluator_name: str
    findings: List[FindingOutput]


class BaseEvaluator(ABC):
    """
    Abstract interface for provider-independent AI evaluators.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'mock_evaluator')."""
        pass

    @abstractmethod
    async def evaluate(self, payload: EvaluationInput) -> EvaluationResult:
        """
        Evaluates a student's authoritative answer against the question prompt,
        rubric, expected answer, and topic context.
        """
        pass

    @abstractmethod
    async def generate_follow_up(self, payload: FollowUpGenerationInput) -> FollowUpQuestionPayload:
        """
        Generates ONE diagnostic follow-up question testing the suspected misconception.
        """
        pass
