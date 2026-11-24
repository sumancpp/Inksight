from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProposalStatus, ReviewAction


class ProposedAnswerRead(BaseModel):
    id: int
    submission_id: int
    upload_id: int
    ocr_extraction_id: int
    question_id: Optional[int] = None
    segment_id: Optional[int] = None
    proposed_text: str
    corrected_text: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: ProposalStatus
    rejection_reason: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnmatchedSegmentInfo(BaseModel):
    segment_id: Optional[int] = None
    page: Optional[int] = 1
    text: str
    confidence: Optional[float] = None
    reason: str


class UnansweredQuestionInfo(BaseModel):
    question_id: int
    sequence_number: int
    prompt: str
    marks: float
    has_existing_answer: bool = False
    existing_answer_text: Optional[str] = None


class AnswerMatchingResponse(BaseModel):
    submission_id: int
    upload_id: int
    assessment_id: int
    total_questions: int
    matched_count: int
    needs_review_count: int
    unmatched_count: int
    proposals: List[ProposedAnswerRead]
    unmatched_segments: List[UnmatchedSegmentInfo]
    unanswered_questions: List[UnansweredQuestionInfo]


class TeacherApproveRequest(BaseModel):
    question_id: Optional[int] = Field(None, description="Optional question ID to assign if currently unassigned")
    review_notes: Optional[str] = Field(None, max_length=1000, description="Optional review notes")


class TeacherCorrectRequest(BaseModel):
    corrected_text: str = Field(..., min_length=1, description="Corrected answer text to overwrite OCR proposal")
    question_id: Optional[int] = Field(None, description="Optional target question ID to assign or reassign within assessment")
    review_notes: Optional[str] = Field(None, max_length=1000, description="Optional review notes")


class TeacherRejectRequest(BaseModel):
    rejection_reason: Optional[str] = Field(None, max_length=255, description="Reason for rejection")
    review_notes: Optional[str] = Field(None, max_length=1000, description="Optional review notes")


class TeacherReviewRead(BaseModel):
    id: int
    proposal_id: int
    submission_id: int
    question_id: Optional[int] = None
    reviewer_id: int
    action: ReviewAction
    original_text: str
    final_text: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposedAnswerReviewResponse(BaseModel):
    proposal: ProposedAnswerRead
    review: TeacherReviewRead
    authoritative_answer_text: Optional[str] = None
