from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import FollowUpQuestionType, FollowUpStatus


class RubricCriterion(BaseModel):
    text: str = Field(..., min_length=3)
    marks: int | float = Field(..., gt=0)


class Rubric(BaseModel):
    criteria: List[RubricCriterion] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_total_marks(self) -> "Rubric":
        total = sum(c.marks for c in self.criteria)
        if total <= 0:
            raise ValueError("Rubric total marks must be greater than 0.")
        return self


FollowUpRubric = Rubric


class FollowUpQuestionPayload(BaseModel):
    """Payload produced by AI evaluator."""
    concept: str = Field(..., min_length=1)
    question_text: str = Field(..., min_length=1)
    expected_answer: str = Field(..., min_length=1)
    rubric: Rubric
    question_type: FollowUpQuestionType = FollowUpQuestionType.SHORT_ANSWER


class FollowUpGenerationInput(BaseModel):
    finding_id: int
    question_prompt: str
    student_answer: str
    misconception_hypothesis: str
    linked_concept: str
    evidence_excerpt: Optional[str] = None


class FollowUpQuestionRead(BaseModel):
    id: int
    finding_id: int
    assessment_id: int
    concept: str
    question_text: str
    expected_answer: str
    rubric: Rubric
    question_type: FollowUpQuestionType
    status: FollowUpStatus
    proposed_by: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    audit_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FollowUpApproveRequest(BaseModel):
    audit_notes: Optional[str] = None


class FollowUpRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)
