from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PendingReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: int
    assessment_id: int
    assessment_title: Optional[str] = None
    submission_id: int
    student_id: int
    student_name: str
    question_id: int
    question_number: Optional[int] = None
    question_prompt: Optional[str] = None
    concept_name: Optional[str] = None
    category: str
    confidence: float
    requires_teacher_review: bool
    acknowledged_uncertainty: bool
    review_status: str
    teacher_corrected: bool = False
    priority_score: int
    priority_reasons: List[str] = Field(default_factory=list)
    brief_text: Optional[str] = None
    misconceptions_count: int = 0
    created_at: datetime


class PendingReviewQueueResponse(BaseModel):
    items: List[PendingReviewItem]
    total: int
    page: int
    page_size: int
    total_pages: int

