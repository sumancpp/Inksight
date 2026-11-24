from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SubmissionStatus


class SubmissionBase(BaseModel):
    status: SubmissionStatus = Field(
        default=SubmissionStatus.DRAFT,
        description="Submission status: draft, submitted, processing, or reviewed",
    )


class SubmissionCreate(BaseModel):
    status: SubmissionStatus = Field(
        default=SubmissionStatus.DRAFT,
        description="Initial submission status (defaults to draft)",
    )


class SubmissionUpdate(BaseModel):
    status: Optional[SubmissionStatus] = Field(None, description="Updated submission status")
    submitted_at: Optional[datetime] = Field(None, description="Timestamp when submitted")


class SubmissionRead(BaseModel):
    id: int
    assessment_id: int
    student_id: int
    status: SubmissionStatus
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionAnswerBase(BaseModel):
    answer_text: Optional[str] = Field(None, description="Student's answer text")
    awarded_marks: Optional[float] = Field(None, ge=0.0, description="Marks awarded for this answer")


class QuestionAnswerCreate(QuestionAnswerBase):
    question_id: int = Field(..., description="ID of the question being answered")


class QuestionAnswerUpdate(BaseModel):
    answer_text: Optional[str] = Field(None, description="Updated answer text")
    awarded_marks: Optional[float] = Field(None, ge=0.0, description="Updated marks awarded")


class QuestionAnswerRead(BaseModel):
    id: int
    submission_id: int
    question_id: int
    answer_text: Optional[str]
    awarded_marks: Optional[float]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
