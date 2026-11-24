from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StudentFollowupEvidenceRead(BaseModel):
    """
    Student-safe follow-up response evidence.
    Excludes teacher answer keys, teacher rationales, uncertainty notes, and internal review comments.
    """
    item_id: int
    question_type: str
    student_answer: str
    is_correct: bool
    score: float
    feedback: Optional[str] = None
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentConceptProgressRead(BaseModel):
    """
    Student-facing topic/concept progress and learning loop status.
    Strictly excludes teacher-only keys and notes.
    """
    topic_id: Optional[int] = None
    topic_name: Optional[str] = None
    concept_name: str
    baseline_diagnostic_gap: str
    baseline_evidence_excerpt: Optional[str] = None
    evidence_count: int = 0
    correct_count: int = 0
    accuracy_percentage: float = 0.0
    outcome_status: str  # "improved", "uncertain", "persisting_gap", "pending_followup"
    status_label: str    # "Improved", "Tentative Progress (Needs Evidence)", "Persisting Gap", "Pending Practice"
    uncertainty_level: str  # "Low", "Moderate", "High"
    uncertainty_rationale: str
    remaining_gaps: Optional[str] = None
    recommended_next_step: str
    followup_responses: List[StudentFollowupEvidenceRead] = []


class StudentProgressReportRead(BaseModel):
    """Student-facing learning loop outcome & progress report across an assessment/submission."""
    submission_id: int
    assessment_id: int
    assessment_title: Optional[str] = None
    total_concepts_tracked: int = 0
    improved_count: int = 0
    uncertain_count: int = 0
    persisting_gap_count: int = 0
    pending_count: int = 0
    concepts: List[StudentConceptProgressRead] = []
    overall_next_step: str
    pedagogical_disclaimer: str = (
        "Formative learning evidence. Practice responses illustrate progress on targeted follow-up exercises. "
        "Single responses reflect tentative progress with elevated uncertainty and do not constitute certified mastery."
    )


class TeacherFollowupEvidenceRead(BaseModel):
    """Teacher-facing record of student practice response with full audit provenance."""
    response_id: int
    session_id: int
    remediation_item_id: int
    item_question_text: str
    item_question_type: str
    difficulty: Optional[str] = None
    student_answer: str
    is_correct: bool
    score: float
    feedback: Optional[str] = None
    submitted_at: datetime


class TeacherInterventionOutcomeRead(BaseModel):
    """
    Teacher-facing intervention outcome detail for a specific diagnostic finding.
    Compares prior diagnostic evidence against follow-up practice evidence.
    """
    finding_id: int
    run_id: int
    question_id: int
    topic_id: Optional[int] = None
    topic_name: Optional[str] = None
    concept_name: str
    student_id: int
    student_name: Optional[str] = None
    submission_id: int

    # 1. Prior Evidence (Diagnostic Baseline)
    prior_category: str
    prior_confidence: float
    prior_evidence_excerpt: Optional[str] = None
    prior_rationale: Optional[str] = None
    prior_uncertainty: Optional[str] = None
    finding_review_status: str
    finding_review_notes: Optional[str] = None

    # 2. Support Given (Intervention Items)
    remediation_items_count: int = 0
    support_summary: str

    # 3. Follow-up Evidence Collected
    evidence_count: int = 0
    correct_count: int = 0
    accuracy_percentage: float = 0.0
    latest_response_at: Optional[datetime] = None
    followup_summary: str
    followup_responses: List[TeacherFollowupEvidenceRead] = []

    # 4. Comparative Outcome & Uncertainty
    outcome_status: str  # "improved", "uncertain", "persisting_gap", "pending_followup"
    outcome_label: str
    uncertainty_level: str
    uncertainty_rationale: str
    performance_comparison: str
    recommended_action: str


class InterventionOutcomesSummary(BaseModel):
    """Teacher-facing compilation of intervention outcomes for a submission or assessment."""
    submission_id: Optional[int] = None
    assessment_id: Optional[int] = None
    total_interventions: int = 0
    improved_count: int = 0
    uncertain_count: int = 0
    persisting_gap_count: int = 0
    pending_count: int = 0
    outcomes: List[TeacherInterventionOutcomeRead] = []
    pedagogical_disclaimer: str = (
        "Intervention outcomes compare initial diagnostic findings with follow-up exercise evidence. "
        "Evidence from single responses carries elevated uncertainty and does not warrant claims of complete concept mastery."
    )

