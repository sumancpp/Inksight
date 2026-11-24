from typing import Any, List, Optional
from sqlalchemy.orm import Session

from app.models.enums import EvaluationStatus, FindingCategory, FindingReviewAction, FindingReviewStatus
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.schemas.evaluation import compute_confidence_level, derive_requires_teacher_review


class EvaluationRepository:
    def get_run_by_id(self, db: Session, run_id: int) -> Optional[EvaluationRun]:
        return db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()

    def get_runs_by_submission(self, db: Session, submission_id: int) -> List[EvaluationRun]:
        return (
            db.query(EvaluationRun)
            .filter(EvaluationRun.submission_id == submission_id)
            .order_by(EvaluationRun.id.desc())
            .all()
        )

    def get_runs_by_question(
        self, db: Session, submission_id: int, question_id: int
    ) -> List[EvaluationRun]:
        return (
            db.query(EvaluationRun)
            .filter(
                EvaluationRun.submission_id == submission_id,
                EvaluationRun.question_id == question_id,
            )
            .order_by(EvaluationRun.id.desc())
            .all()
        )

    def get_run_by_hash(
        self, db: Session, submission_id: int, question_id: int, answer_text_hash: str
    ) -> Optional[EvaluationRun]:
        return (
            db.query(EvaluationRun)
            .filter(
                EvaluationRun.submission_id == submission_id,
                EvaluationRun.question_id == question_id,
                EvaluationRun.answer_text_hash == answer_text_hash,
            )
            .first()
        )

    def create_run(
        self,
        db: Session,
        submission_id: int,
        question_id: int,
        question_answer_id: int,
        evaluator_name: str,
        answer_text_hash: str,
        answer_text_snapshot: str,
        status: EvaluationStatus = EvaluationStatus.PENDING,
    ) -> EvaluationRun:
        run = EvaluationRun(
            submission_id=submission_id,
            question_id=question_id,
            question_answer_id=question_answer_id,
            evaluator_name=evaluator_name,
            answer_text_hash=answer_text_hash,
            answer_text_snapshot=answer_text_snapshot,
            status=status.value if hasattr(status, "value") else status,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def create_finding(
        self,
        db: Session,
        run_id: int,
        concept_name: Optional[str],
        category: FindingCategory,
        confidence: float,
        rationale: str,
        evidence_excerpt: Optional[str] = None,
        uncertainty_rationale: Optional[str] = None,
        topic_id: Optional[int] = None,
        verdict: Optional[str] = None,
        correct_answer: Optional[str] = None,
        marks_awarded: Optional[float] = None,
        max_marks: Optional[float] = None,
        marks_reason: Optional[str] = None,
        error_amount: Optional[str] = None,
        error_type: Optional[str] = None,
        step_by_step_explanation: Optional[str] = None,
        misconception_hypothesis: Optional[str] = None,
        remediation_concept: Optional[str] = None,
        follow_up_question: Optional[str] = None,
        misconceptions: Optional[List[Any]] = None,
        confidence_details: Optional[Any] = None,
        requires_teacher_review: bool = False,
    ) -> EvaluationFinding:
        cat_val = category.value if hasattr(category, "value") else category

        serialized_misconceptions = []
        if misconceptions:
            for item in misconceptions:
                if hasattr(item, "model_dump"):
                    serialized_misconceptions.append(item.model_dump())
                elif isinstance(item, dict):
                    serialized_misconceptions.append(item)

        serialized_confidence = None
        if confidence_details:
            if hasattr(confidence_details, "model_dump"):
                serialized_confidence = confidence_details.model_dump()
            elif isinstance(confidence_details, dict):
                serialized_confidence = confidence_details

        # Single source of truth enforcement at write-time:
        if serialized_confidence and "score" in serialized_confidence:
            score = float(serialized_confidence["score"])
            confidence = score
            derived_level = compute_confidence_level(score)
            serialized_confidence["level"] = derived_level
            requires_teacher_review = derive_requires_teacher_review(serialized_confidence)

        legacy_misconception = None
        if serialized_misconceptions and len(serialized_misconceptions) > 0:
            legacy_misconception = serialized_misconceptions[0].get("hypothesis")
        elif misconception_hypothesis:
            legacy_misconception = misconception_hypothesis

        finding = EvaluationFinding(
            run_id=run_id,
            topic_id=topic_id,
            concept_name=concept_name,
            category=cat_val,
            confidence=confidence,
            uncertainty_rationale=uncertainty_rationale,
            evidence_excerpt=evidence_excerpt,
            rationale=rationale,
            verdict=verdict,
            correct_answer=correct_answer,
            marks_awarded=marks_awarded,
            max_marks=max_marks,
            marks_reason=marks_reason,
            error_amount=error_amount,
            error_type=error_type,
            step_by_step_explanation=step_by_step_explanation,
            remediation_concept=remediation_concept,
            follow_up_question=follow_up_question,
            misconceptions=serialized_misconceptions,
            confidence_details=serialized_confidence,
            requires_teacher_review=requires_teacher_review,
            review_status=FindingReviewStatus.PENDING_REVIEW.value,
        )
        finding.misconception_hypothesis = legacy_misconception
        db.add(finding)
        db.commit()
        db.refresh(finding)
        return finding

    def get_finding_by_id(self, db: Session, finding_id: int) -> Optional[EvaluationFinding]:
        return db.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()

    def create_finding_review_audit(
        self,
        db: Session,
        finding_id: Optional[int],
        reviewer_id: Optional[int],
        action: FindingReviewAction | str,
        review_notes: Optional[str] = None,
        acknowledged_uncertainty: bool = False,
    ) -> FindingReviewAudit:
        act_val = action.value if hasattr(action, "value") else action
        audit = FindingReviewAudit(
            finding_id=finding_id,
            reviewer_id=reviewer_id,
            action=act_val,
            review_notes=review_notes,
            acknowledged_uncertainty=acknowledged_uncertainty,
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit


evaluation_repository = EvaluationRepository()
