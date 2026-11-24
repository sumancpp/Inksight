from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InferredQAItem(BaseModel):
    id: Optional[int] = None
    question_number: int = Field(..., description="Logical question sequence number (1, 2, ...)")
    inferred_question: str = Field(..., description="AI inferred question prompt")
    student_answer: str = Field(..., description="Extracted student answer and work")
    concept_name: str = Field(..., description="Subject concept name")
    expected_answer: Optional[str] = Field(None, description="Authoritative reference solution")
    rubric: Optional[str] = Field(None, description="Grading criteria")
    verdict: str = Field(default="correct", description="correct, partially_correct, incorrect, or needs_teacher_review")
    category: str = Field(default="correct_understanding", description="correct_understanding, partially_correct_understanding, likely_misconception, or insufficient_evidence")
    marks_awarded: float = Field(default=5.0, description="Marks awarded to student")
    max_marks: float = Field(default=5.0, description="Total marks available for question")
    step_by_step_explanation: Optional[str] = Field(None, description="Diagnostic explanation of work")
    misconceptions: List[Dict[str, Any]] = Field(default_factory=list, description="Hypothesized student misconceptions")
    confidence: float = Field(default=0.85, description="Diagnostic confidence score (0.0 to 1.0)")
    confidence_details: Optional[Dict[str, Any]] = Field(default=None, description="Structured confidence breakdown")
    requires_teacher_review: bool = Field(default=False, description="Flag indicating teacher review gate")
    evidence_excerpt: Optional[str] = Field(None, description="Exact quote from student answer")
    question_id: Optional[int] = Field(None, description="Associated Question database ID")
    finding_id: Optional[int] = Field(None, description="Associated EvaluationFinding database ID")
    proposal_id: Optional[int] = Field(None, description="Associated ProposedAnswer database ID")


class InferredQAUpdateRequest(BaseModel):
    inferred_question: Optional[str] = Field(None, description="Updated question text edited by teacher")
    expected_answer: Optional[str] = Field(None, description="Updated reference answer edited by teacher")
    re_evaluate: bool = Field(default=True, description="Whether to re-evaluate the student answer after teacher edit")


class InferredQAResponse(BaseModel):
    upload_id: int
    submission_id: int
    assessment_id: int
    mode: str = "inferred_questions"
    total_inferred: int
    items: List[InferredQAItem]
    evaluation_summary: Optional[Dict[str, Any]] = None

