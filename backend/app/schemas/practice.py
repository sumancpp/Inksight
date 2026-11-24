from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PracticeQuestionType, PracticeSessionStatus


class PracticeResponseSubmit(BaseModel):
    """Payload for student submitting an answer to an approved remediation practice item."""
    remediation_item_id: int = Field(..., description="ID of the approved remediation practice item")
    student_answer: str = Field(..., min_length=1, max_length=5000, description="Student's answer text")


class PracticeResponseRead(BaseModel):
    """
    Student-safe response feedback.
    Strictly excludes teacher_answer_key, teacher_rationale, and review_notes.
    """
    id: int
    session_id: int
    remediation_item_id: int
    student_answer: str
    is_correct: bool
    score: float
    feedback: Optional[str] = None
    finding_id: int
    evaluation_run_id: int
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PracticeSessionItemRead(BaseModel):
    """
    Student-facing deliverable item within a practice session.
    Strictly excludes teacher answer keys, rationales, uncertainty notes, and reviewer details.
    """
    id: int
    finding_id: int
    target_concept: Optional[str] = None
    question_text: str
    question_type: PracticeQuestionType
    options: Optional[List[str]] = None
    difficulty: Optional[str] = None
    answered: bool = False
    response: Optional[PracticeResponseRead] = None

    model_config = ConfigDict(from_attributes=True)


class PracticeSessionRead(BaseModel):
    """Practice session metadata."""
    id: int
    student_id: int
    submission_id: int
    status: PracticeSessionStatus
    total_items: int
    completed_items: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PracticeSessionDetailRead(PracticeSessionRead):
    """Practice session with deliverable items and existing responses."""
    items: List[PracticeSessionItemRead] = []
    responses: List[PracticeResponseRead] = []


class ConceptPracticeProgress(BaseModel):
    """Concept-level formative practice evidence breakdown."""
    concept_name: str
    items_count: int
    correct_count: int
    evidence_summary: str
    remaining_gaps: Optional[str] = None
    recommended_next_step: Optional[str] = None
    outcome_status: Optional[str] = None
    uncertainty_level: Optional[str] = None


class PracticeSessionSummary(BaseModel):
    """
    Formative practice summary report.
    Presents deterministic scoring and concept progress while explicitly avoiding
    unsupported claims of mastery from single responses.
    """
    session_id: int
    submission_id: int
    status: PracticeSessionStatus
    total_items: int
    completed_items: int
    correct_count: int
    total_score: float
    max_score: float
    accuracy_percentage: float
    concepts_practiced: List[ConceptPracticeProgress] = []
    pedagogical_disclaimer: str = (
        "Formative practice feedback. Note: Practice response scores represent formative exercise evidence, "
        "not certified concept mastery."
    )
