from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EvaluationStatus, FindingCategory, FindingReviewAction, FindingReviewStatus


def compute_confidence_level(score: float) -> Literal["low", "medium", "high"]:
    if score < 0.70:
        return "low"
    elif score < 0.85:
        return "medium"
    return "high"


def derive_requires_teacher_review(confidence_details: Optional[Union["ConfidenceDetails", dict]] = None) -> bool:
    """Canonical derivation helper: score is truth, level 'low' requires teacher review."""
    if not confidence_details:
        return False
    if isinstance(confidence_details, dict):
        level = confidence_details.get("level")
        if not level and "score" in confidence_details:
            level = compute_confidence_level(float(confidence_details["score"]))
        return level == "low"
    return bool(getattr(confidence_details, "level", None) == "low")


class MisconceptionItem(BaseModel):
    hypothesis: str
    evidence_excerpt: str
    linked_concept: str
    severity: Optional[Literal["low", "medium", "high"]] = None
    # evidence_location intentionally OMITTED — cannot be server-validated.


class ConfidenceDetails(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    level: Literal["low", "medium", "high"] = "low"
    uncertainty_reasons: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def derive_level_from_score(self) -> "ConfidenceDetails":
        # Score is truth: model-provided level is advisory only; overwrite with derived value
        self.level = compute_confidence_level(self.score)
        return self


class FindingOutput(BaseModel):
    concept_name: Optional[str] = None
    category: FindingCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    uncertainty_rationale: Optional[str] = None
    evidence_excerpt: Optional[str] = None
    rationale: str
    verdict: Optional[str] = Field(None, description="Diagnostic correctness: correct, partially_correct, incorrect, or needs_teacher_review")
    correct_answer: Optional[str] = Field(None, description="Proposed or teacher-approved correct answer / key points")
    marks_awarded: Optional[float] = Field(None, ge=0.0, description="Marks awarded based on rubric / exactness")
    max_marks: Optional[float] = Field(None, ge=0.0, description="Total marks available for the question")
    marks_reason: Optional[str] = Field(None, description="Short justification for marks awarded")
    error_amount: Optional[str] = Field(None, description="Numerical error amount when applicable, e.g. '+1'")
    error_type: Optional[str] = Field(None, description="Error classification: numerical_difference, wrong_unit, missing_step, misconception, omitted_key_point")
    step_by_step_explanation: Optional[str] = Field(None, description="Pedagogical step-by-step breakdown of error and correction")
    misconception_hypothesis: Optional[str] = Field(None, description="Hypothesized misconception or prerequisite gap")
    remediation_concept: Optional[str] = Field(None, description="Targeted concept or skill to review")
    follow_up_question: Optional[str] = Field(None, description="Targeted check question to verify if gap is resolved")
    misconceptions: List[MisconceptionItem] = Field(default_factory=list)
    confidence_details: Optional[ConfidenceDetails] = None
    requires_teacher_review: bool = False

    @model_validator(mode="after")
    def sync_derived_fields(self) -> "FindingOutput":
        # Single Source of Truth: confidence scalar is derived from confidence_details.score
        if self.confidence_details is not None:
            self.confidence_details.level = compute_confidence_level(self.confidence_details.score)
            self.confidence = self.confidence_details.score
            self.requires_teacher_review = derive_requires_teacher_review(self.confidence_details)
        elif self.confidence is not None:
            level = compute_confidence_level(self.confidence)
            self.confidence_details = ConfidenceDetails(score=self.confidence, level=level, uncertainty_reasons=[])
            self.requires_teacher_review = derive_requires_teacher_review(self.confidence_details)

        # Single Source of Truth: misconception_hypothesis is derived from misconceptions[0].hypothesis
        if self.misconceptions and len(self.misconceptions) > 0:
            self.misconception_hypothesis = self.misconceptions[0].hypothesis
        return self


class EvaluationFindingRead(BaseModel):
    id: int
    run_id: int
    topic_id: Optional[int] = None
    concept_name: Optional[str] = None
    category: FindingCategory
    confidence: float
    uncertainty_rationale: Optional[str] = None
    evidence_excerpt: Optional[str] = None
    rationale: str
    verdict: Optional[str] = None
    correct_answer: Optional[str] = None
    marks_awarded: Optional[float] = None
    max_marks: Optional[float] = None
    marks_reason: Optional[str] = None
    error_amount: Optional[str] = None
    error_type: Optional[str] = None
    step_by_step_explanation: Optional[str] = None
    misconception_hypothesis: Optional[str] = None
    remediation_concept: Optional[str] = None
    follow_up_question: Optional[str] = None
    review_status: FindingReviewStatus
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    misconceptions: List[MisconceptionItem] = Field(default_factory=list)
    confidence_details: Optional[ConfidenceDetails] = None
    requires_teacher_review: bool = False
    acknowledged_uncertainty: bool = False
    teacher_corrected: bool = False

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def derive_legacy_fields(self) -> "EvaluationFindingRead":
        # Single Source of Truth: confidence scalar is derived from confidence_details.score
        if self.confidence_details is not None:
            self.confidence_details.level = compute_confidence_level(self.confidence_details.score)
            self.confidence = self.confidence_details.score
            self.requires_teacher_review = derive_requires_teacher_review(self.confidence_details)
        elif self.confidence is not None:
            level = compute_confidence_level(self.confidence)
            self.confidence_details = ConfidenceDetails(score=self.confidence, level=level, uncertainty_reasons=[])
            self.requires_teacher_review = derive_requires_teacher_review(self.confidence_details)

        # Single Source of Truth: misconception_hypothesis is derived from misconceptions[0].hypothesis
        if self.misconceptions and len(self.misconceptions) > 0:
            self.misconception_hypothesis = self.misconceptions[0].hypothesis
        return self


class FindingReviewAuditRead(BaseModel):
    id: int
    finding_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    action: FindingReviewAction
    review_notes: Optional[str] = None
    acknowledged_uncertainty: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunRead(BaseModel):
    id: int
    submission_id: int
    question_id: int
    question_answer_id: int
    evaluator_name: str
    status: EvaluationStatus
    answer_text_hash: str
    answer_text_snapshot: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationRunDetailRead(EvaluationRunRead):
    findings: List[EvaluationFindingRead] = []


class FindingReviewRequest(BaseModel):
    action: FindingReviewAction = Field(..., description="Review action: accepted, rejected, or needs_revision")
    review_notes: Optional[str] = Field(None, max_length=1000, description="Optional teacher review notes")
    acknowledge_uncertainty: bool = Field(False, description="Explicit acknowledgment required to accept low-confidence findings")


class FindingReviewResponse(BaseModel):
    finding: EvaluationFindingRead
    audit: FindingReviewAuditRead


class SubmissionEvaluationSummary(BaseModel):
    submission_id: int
    total_runs: int
    runs: List[EvaluationRunDetailRead] = []


class AsyncTaskAcceptedResponse(BaseModel):
    task_id: str
    status: str = "ACCEPTED"
    message: str = "Task queued for background execution."
    submission_id: Optional[int] = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    ready: bool = False
    successful: Optional[bool] = None
    result: Optional[Any] = None
    findings: Optional[List[Any]] = None
    error: Optional[str] = None
