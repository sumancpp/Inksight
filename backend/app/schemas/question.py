from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QuestionType


class QuestionBase(BaseModel):
    prompt: str = Field(..., min_length=1, description="Question text or prompt")
    question_type: QuestionType = Field(
        default=QuestionType.MULTIPLE_CHOICE,
        description="Type of question (multiple_choice, short_answer, numerical, essay)",
    )
    marks: float = Field(default=1.0, ge=0.0, description="Marks allotted for this question")
    rubric: Optional[str] = Field(None, description="Teacher-provided rubric or grading criteria")
    expected_answer: Optional[str] = Field(None, description="Teacher-provided expected answer or model solution")
    is_reference_proposed: bool = Field(default=False, description="Whether the expected answer/rubric was AI-proposed and requires teacher review")
    reference_status: str = Field(default="approved", description="Status of reference key: 'approved', 'proposed', 'needs_review'")


class QuestionCreate(QuestionBase):
    topic_id: int = Field(..., description="ID of associated learning topic")
    assessment_id: Optional[int] = Field(None, description="ID of parent assessment (can be inferred from route path)")


class QuestionUpdate(BaseModel):
    prompt: Optional[str] = Field(None, min_length=1)
    question_type: Optional[QuestionType] = None
    marks: Optional[float] = Field(None, ge=0.0)
    topic_id: Optional[int] = None
    rubric: Optional[str] = None
    expected_answer: Optional[str] = None
    is_reference_proposed: Optional[bool] = None
    reference_status: Optional[str] = None


class ApproveReferenceRequest(BaseModel):
    expected_answer: Optional[str] = Field(None, description="Optional updated or confirmed expected answer")
    rubric: Optional[str] = Field(None, description="Optional updated or confirmed rubric")


class QuestionRead(QuestionBase):
    id: int
    assessment_id: int
    topic_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

