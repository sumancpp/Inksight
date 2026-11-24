from datetime import datetime, timezone
import hashlib
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.models.assessment import Question
from app.models.enums import (
    EvaluationStatus,
    FindingReviewAction,
    FindingReviewStatus,
    InvalidStateTransitionError,
    ProposalStatus,
    ReviewAction,
    UserRole,
    validate_finding_review_transition,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.submission import QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.repositories.evaluation_repository import evaluation_repository
from app.schemas.evaluation import (
    ConfidenceDetails,
    EvaluationFindingRead,
    EvaluationRunDetailRead,
    FindingReviewAuditRead,
    FindingReviewRequest,
    FindingReviewResponse,
    MisconceptionItem,
    SubmissionEvaluationSummary,
    derive_requires_teacher_review,
)
from app.services.evaluator.base import EvaluationInput
from app.services.evaluator.factory import get_evaluator


class EvaluationService:
    @staticmethod
    def compute_answer_hash(answer_text: str) -> str:
        """
        Computes SHA-256 hash of authoritative answer text for versioning and provenance.
        """
        normalized = answer_text.strip().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    def _validate_reviewer(self, db: Session, reviewer_id: int) -> User:
        reviewer = db.query(User).filter(User.id == reviewer_id).first()
        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reviewer with id {reviewer_id} not found.",
            )
        if reviewer.role not in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Reviewer user {reviewer_id} does not have the teacher or admin role.",
            )
        return reviewer

    def _assert_authoritative_answer_reviewed(
        self, db: Session, submission_id: int, question_id: int, qa: QuestionAnswer
    ) -> None:
        """
        Safety Guard:
        Verifies that QuestionAnswer.answer_text is non-empty and has been explicitly
        approved or corrected by a teacher. Unreviewed proposals are NEVER evaluated.
        """
        if not qa.answer_text or not qa.answer_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"QuestionAnswer for question {question_id} has no answer text to evaluate.",
            )

        # Check for teacher review approval/correction record
        approved_review = (
            db.query(TeacherReview)
            .filter(
                TeacherReview.submission_id == submission_id,
                TeacherReview.question_id == question_id,
                TeacherReview.action.in_([ReviewAction.APPROVE.value, ReviewAction.CORRECT.value]),
            )
            .first()
        )

        # Check for approved/corrected proposal status
        approved_proposal = (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.submission_id == submission_id,
                ProposedAnswer.question_id == question_id,
                ProposedAnswer.status.in_([ProposalStatus.APPROVED.value, ProposalStatus.CORRECTED.value]),
            )
            .first()
        )

        # Check if unreviewed proposals exist for this question
        unreviewed_proposal = (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.submission_id == submission_id,
                ProposedAnswer.question_id == question_id,
                ProposedAnswer.status.in_([
                    ProposalStatus.PROPOSED.value,
                    ProposalStatus.NEEDS_REVIEW.value,
                ]),
            )
            .first()
        )

        is_approved = (approved_review is not None) or (approved_proposal is not None)

        if not is_approved or unreviewed_proposal is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot evaluate an unreviewed or unapproved answer. Explicit teacher approval or correction is required.",
            )

    async def evaluate_question_answer(
        self, db: Session, submission_id: int, question_id: int
    ) -> EvaluationRunDetailRead:
        """
        Evaluates a single question's authoritative answer.
        Guarantees:
        - Evaluates ONLY teacher-approved/corrected answers.
        - Idempotent against identical answer version (same SHA-256 hash).
        - Preserves exact answer text snapshot and hash for audit provenance.
        - Never mutates QuestionAnswer, ProposedAnswer, or OCRExtraction.
        """
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question with id {question_id} not found.",
            )

        if question.assessment_id != submission.assessment_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Question does not belong to the submission's assessment.",
            )

        if getattr(question, "is_reference_proposed", False) or getattr(question, "reference_status", "approved") == "proposed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Question has an unapproved AI-proposed reference answer or rubric. Explicit teacher review and approval is required before evaluation.",
            )

        qa = (
            db.query(QuestionAnswer)
            .filter(
                QuestionAnswer.submission_id == submission_id,
                QuestionAnswer.question_id == question_id,
            )
            .first()
        )
        if not qa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No answer record found for question id {question_id}.",
            )

        # Enforce teacher review requirement
        self._assert_authoritative_answer_reviewed(db, submission_id, question_id, qa)

        answer_hash = self.compute_answer_hash(qa.answer_text)

        # Idempotency check: if completed run exists for this exact answer hash, return it
        existing_run = evaluation_repository.get_run_by_hash(
            db=db,
            submission_id=submission_id,
            question_id=question_id,
            answer_text_hash=answer_hash,
        )
        if existing_run and existing_run.status == EvaluationStatus.COMPLETED.value:
            logger.info(
                f"EvaluationRun already completed for submission {submission_id}, question {question_id}, hash {answer_hash[:8]}. Reusing existing run."
            )
            return EvaluationRunDetailRead.model_validate(existing_run)

        evaluator = get_evaluator()
        topic = db.query(LearningTopic).filter(LearningTopic.id == question.topic_id).first()

        eval_input = EvaluationInput(
            question_prompt=question.prompt,
            expected_answer=question.expected_answer,
            rubric=question.rubric,
            topic_name=topic.name if topic else None,
            student_answer=qa.answer_text,
            marks=question.marks if question.marks is not None else 1.0,
            question_type=question.question_type,
        )

        # Create or update run record
        if existing_run:
            run = existing_run
            # Fix C: Purge audit safety & supersede logic
            existing_findings = (
                db.query(EvaluationFinding)
                .filter(EvaluationFinding.run_id == run.id)
                .all()
            )
            for f in existing_findings:
                # Check if finding has ANY prior FindingReviewAudit rows with teacher-reviewed actions
                has_teacher_audit = (
                    db.query(FindingReviewAudit)
                    .filter(
                        FindingReviewAudit.finding_id == f.id,
                        FindingReviewAudit.action.in_([
                            FindingReviewAction.ACCEPT.value,
                            FindingReviewAction.REJECT.value,
                            FindingReviewAction.REQUEST_REVISION.value,
                        ]),
                    )
                    .first()
                    is not None
                    or f.review_status in [
                        FindingReviewStatus.ACCEPTED.value,
                        FindingReviewStatus.REJECTED.value,
                        FindingReviewStatus.NEEDS_REVISION.value,
                    ]
                )
                if has_teacher_audit:
                    # SUPERSEDE instead of DELETE: set old finding.review_status="superseded", add audit
                    prior_status = f.review_status
                    f.review_status = FindingReviewStatus.SUPERSEDED.value
                    f.reviewed_at = datetime.now(timezone.utc)
                    db.flush()
                    evaluation_repository.create_finding_review_audit(
                        db=db,
                        finding_id=f.id,
                        reviewer_id=None,
                        action=FindingReviewAction.SUPERSEDE.value,
                        review_notes=f"[system] Superseded for re-evaluation, prior review_status={prior_status}",
                        acknowledged_uncertainty=False,
                    )
                else:
                    # BEFORE deleting pending finding, write a row to FindingReviewAudit with system actor
                    prior_status = f.review_status
                    evaluation_repository.create_finding_review_audit(
                        db=db,
                        finding_id=None,
                        reviewer_id=None,
                        action="purged",
                        review_notes=f"[system] Purged for re-evaluation, prior review_status={prior_status}",
                        acknowledged_uncertainty=False,
                    )
                    db.delete(f)
            run.status = EvaluationStatus.PENDING.value
            run.evaluator_name = evaluator.provider_name
            db.commit()
        else:
            run = evaluation_repository.create_run(
                db=db,
                submission_id=submission_id,
                question_id=question_id,
                question_answer_id=qa.id,
                evaluator_name=evaluator.provider_name,
                answer_text_hash=answer_hash,
                answer_text_snapshot=qa.answer_text,
                status=EvaluationStatus.PENDING,
            )

        try:
            is_fallback = False
            try:
                eval_result = await evaluator.evaluate(eval_input)
            except Exception as eval_err:
                from app.services.evaluator.base import EvaluatorError
                import httpx
                is_evaluator_unreachable = isinstance(eval_err, (EvaluatorError, httpx.HTTPError)) or (
                    hasattr(eval_err, "error_code") and getattr(eval_err, "error_code") in ["VLLM_CONNECTION_FAILED", "VLLM_TIMEOUT", "VLLM_API_ERROR", "VLLM_TRANSPORT_ERROR"]
                )
                if settings.ENABLE_EVALUATOR_FALLBACK and is_evaluator_unreachable:
                    logger.warning(
                        f"AI evaluator failed ({eval_err}). Gracefully falling back to mock evaluator."
                    )
                    from app.services.evaluator.mock_evaluator import MockEvaluator
                    fallback_eval = MockEvaluator()
                    eval_result = await fallback_eval.evaluate(eval_input)
                    is_fallback = True
                else:
                    raise eval_err

            if is_fallback:
                run.evaluator_name = f"{evaluator.provider_name} (fallback: mock)"
            else:
                run.evaluator_name = eval_result.evaluator_name
            norm_student = " ".join((qa.answer_text or "").lower().split())

            for finding in eval_result.findings:
                if is_fallback:
                    fallback_msg = "AI is currently offline. Showing cached or mock evaluation."
                    if finding.uncertainty_rationale:
                        finding.uncertainty_rationale = f"{fallback_msg} {finding.uncertainty_rationale}"
                    else:
                        finding.uncertainty_rationale = fallback_msg
                    if finding.confidence_details:
                        if "ai_offline_fallback" not in finding.confidence_details.uncertainty_reasons:
                            finding.confidence_details.uncertainty_reasons.append("ai_offline_fallback")
                # 1. Grounding validation for structured misconceptions
                grounded_misconceptions: List[MisconceptionItem] = []
                attempted_misconceptions = len(finding.misconceptions or [])
                for item in (finding.misconceptions or []):
                    norm_item_excerpt = " ".join((item.evidence_excerpt or "").lower().split())
                    if norm_item_excerpt and norm_item_excerpt in norm_student:
                        grounded_misconceptions.append(item)
                    else:
                        logger.warning(
                            f"EvaluationService: Dropping ungrounded misconception excerpt '{item.evidence_excerpt}'."
                        )

                finding.misconceptions = grounded_misconceptions

                # 2. Derive/verify confidence_details: score is truth
                if not finding.confidence_details:
                    score = float(finding.confidence if finding.confidence is not None else 0.5)
                    level = "low" if score < 0.70 else ("medium" if score < 0.85 else "high")
                    finding.confidence_details = ConfidenceDetails(score=score, level=level, uncertainty_reasons=[])
                else:
                    score = float(finding.confidence_details.score)
                    derived_level = "low" if score < 0.70 else ("medium" if score < 0.85 else "high")
                    finding.confidence_details.level = derived_level

                # If all attempted misconceptions were ungrounded and dropped, cap score and set level = "low"
                if attempted_misconceptions > 0 and len(grounded_misconceptions) == 0:
                    finding.confidence_details.score = min(finding.confidence_details.score, 0.50)
                    finding.confidence_details.level = "low"
                    if "no_grounded_misconception_evidence" not in finding.confidence_details.uncertainty_reasons:
                        finding.confidence_details.uncertainty_reasons.append("no_grounded_misconception_evidence")

                finding.requires_teacher_review = derive_requires_teacher_review(finding.confidence_details)
                finding.confidence = finding.confidence_details.score
                if finding.misconceptions and len(finding.misconceptions) > 0:
                    finding.misconception_hypothesis = finding.misconceptions[0].hypothesis
                elif attempted_misconceptions > 0 and len(grounded_misconceptions) == 0:
                    finding.misconception_hypothesis = None

                evaluation_repository.create_finding(
                    db=db,
                    run_id=run.id,
                    concept_name=finding.concept_name,
                    category=finding.category,
                    confidence=finding.confidence,
                    rationale=finding.rationale,
                    evidence_excerpt=finding.evidence_excerpt,
                    uncertainty_rationale=finding.uncertainty_rationale,
                    topic_id=question.topic_id,
                    verdict=finding.verdict,
                    correct_answer=finding.correct_answer or question.expected_answer,
                    marks_awarded=finding.marks_awarded,
                    max_marks=finding.max_marks or question.marks,
                    marks_reason=finding.marks_reason,
                    error_amount=finding.error_amount,
                    error_type=finding.error_type,
                    step_by_step_explanation=finding.step_by_step_explanation,
                    misconception_hypothesis=finding.misconception_hypothesis,
                    remediation_concept=finding.remediation_concept,
                    follow_up_question=finding.follow_up_question,
                    misconceptions=finding.misconceptions,
                    confidence_details=finding.confidence_details,
                    requires_teacher_review=finding.requires_teacher_review,
                )

                # Update authoritative QuestionAnswer awarded marks if provided
                if finding.marks_awarded is not None:
                    qa.awarded_marks = finding.marks_awarded

            run.status = EvaluationStatus.COMPLETED.value
            db.commit()
            db.refresh(run)
            logger.info(
                f"Successfully completed evaluation run {run.id} with {len(eval_result.findings)} findings."
            )
            return EvaluationRunDetailRead.model_validate(run)
        except Exception as exc:
            run.status = EvaluationStatus.FAILED.value
            run.error_message = str(exc)
            db.commit()
            logger.error(f"EvaluationRun {run.id} failed: {exc}", exc_info=True)
            from app.services.evaluator.base import EvaluatorError
            if isinstance(exc, EvaluatorError):
                status_code = (
                    status.HTTP_502_BAD_GATEWAY
                    if exc.error_code in ["VLLM_CONNECTION_FAILED", "VLLM_TIMEOUT"]
                    else status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                raise HTTPException(
                    status_code=status_code,
                    detail=str(exc),
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Evaluation processing failed.",
            )

    async def evaluate_submission(
        self, db: Session, submission_id: int
    ) -> SubmissionEvaluationSummary:
        """
        Evaluates all teacher-approved answers for an assessment submission.
        """
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        runs: List[EvaluationRunDetailRead] = []
        for qa in submission.answers:
            if not qa.answer_text or not qa.answer_text.strip():
                continue

            try:
                run_detail = await self.evaluate_question_answer(
                    db=db, submission_id=submission.id, question_id=qa.question_id
                )
                runs.append(run_detail)
            except HTTPException as e:
                # If an answer has not been teacher-reviewed yet, skip it in batch submission evaluation
                if e.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                    logger.info(
                        f"Skipping question {qa.question_id} during batch evaluation: {e.detail}"
                    )
                    continue
                raise

        return SubmissionEvaluationSummary(
            submission_id=submission.id,
            total_runs=len(runs),
            runs=runs,
        )

    def get_run(self, db: Session, run_id: int) -> EvaluationRunDetailRead:
        run = evaluation_repository.get_run_by_id(db=db, run_id=run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation run with id {run_id} not found.",
            )
        return EvaluationRunDetailRead.model_validate(run)

    def get_submission_evaluations(
        self, db: Session, submission_id: int
    ) -> SubmissionEvaluationSummary:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )

        runs = evaluation_repository.get_runs_by_submission(db=db, submission_id=submission_id)
        return SubmissionEvaluationSummary(
            submission_id=submission_id,
            total_runs=len(runs),
            runs=[EvaluationRunDetailRead.model_validate(r) for r in runs],
        )

    def get_question_evaluations(
        self, db: Session, submission_id: int, question_id: int
    ) -> List[EvaluationRunDetailRead]:
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )
        question = db.query(Question).filter(Question.id == question_id).first()
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Question with id {question_id} not found.",
            )
        if question.assessment_id != submission.assessment_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Question does not belong to the submission's assessment.",
            )
        runs = evaluation_repository.get_runs_by_question(
            db=db, submission_id=submission_id, question_id=question_id
        )
        return [EvaluationRunDetailRead.model_validate(r) for r in runs]

    def review_finding(
        self, db: Session, finding_id: int, reviewer_id: int, request: FindingReviewRequest
    ) -> FindingReviewResponse:
        """
        Allows a teacher to review a conceptual finding:
        - Validates reviewer role is 'teacher' or 'admin'
        - Validates valid state transition
        - Records audit log in finding_review_audits
        - Updates finding review status and notes
        """
        reviewer = self._validate_reviewer(db, reviewer_id)

        finding = evaluation_repository.get_finding_by_id(db=db, finding_id=finding_id)
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Finding with id {finding_id} not found.",
            )

        # Review Gate Enforcement:
        # If finding requires teacher review (low confidence) and action is ACCEPT,
        # explicit acknowledgment of uncertainty is required.
        if (
            finding.requires_teacher_review
            and request.action == FindingReviewAction.ACCEPT
            and not request.acknowledge_uncertainty
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Low-confidence finding requires explicit acknowledgement.",
            )

        target_status_map = {
            FindingReviewAction.ACCEPT: FindingReviewStatus.ACCEPTED,
            FindingReviewAction.REJECT: FindingReviewStatus.REJECTED,
            FindingReviewAction.REQUEST_REVISION: FindingReviewStatus.NEEDS_REVISION,
        }
        target_status = target_status_map[request.action]

        try:
            validate_finding_review_transition(finding.review_status, target_status)
        except InvalidStateTransitionError as err:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(err))

        review_notes = request.review_notes or ""
        if finding.requires_teacher_review and request.acknowledge_uncertainty:
            ack_msg = "[Teacher explicitly acknowledged diagnostic uncertainty]"
            review_notes = f"{review_notes}\n{ack_msg}".strip() if review_notes else ack_msg

        audit = evaluation_repository.create_finding_review_audit(
            db=db,
            finding_id=finding.id,
            reviewer_id=reviewer.id,
            action=request.action,
            review_notes=review_notes,
            acknowledged_uncertainty=request.acknowledge_uncertainty,
        )

        finding.review_status = target_status.value
        finding.reviewed_by = reviewer.id
        finding.reviewed_at = datetime.now(timezone.utc)
        finding.review_notes = review_notes
        finding.acknowledged_uncertainty = request.acknowledge_uncertainty

        db.commit()
        db.refresh(finding)

        logger.info(
            f"Teacher {reviewer.id} reviewed finding {finding.id} -> action='{request.action.value}'"
        )
        return FindingReviewResponse(
            finding=EvaluationFindingRead.model_validate(finding),
            audit=FindingReviewAuditRead.model_validate(audit),
        )


evaluation_service = EvaluationService()
