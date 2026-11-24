from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models.assessment import Question
from app.models.enums import (
    CorrectionFieldName,
    FindingCategory,
    FindingReviewStatus,
    InvalidStateTransitionError,
    PracticeItemReviewAction,
    PracticeItemReviewStatus,
    RemediationRunStatus,
    UserRole,
    validate_practice_item_transition,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.repositories.remediation_repository import remediation_repository
from app.services.correction_service import resolve_finding_field
from app.schemas.remediation import (
    PracticeItemReviewRequest,
    PracticeItemReviewResponse,
    RemediationItemAuditRead,
    RemediationItemTeacherRead,
    RemediationRunDetailRead,
    RemediationRunRead,
)
from app.services.remediation_generator.base import RemediationInput
from app.services.remediation_generator.factory import get_remediation_generator


class RemediationService:
    def _validate_reviewer(self, db: Session, reviewer_id: int) -> User:
        """
        Validates teacher reviewer identity.
        """
        reviewer = db.query(User).filter(User.id == reviewer_id).first()
        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reviewer user with id {reviewer_id} not found.",
            )
        if reviewer.role not in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Reviewer user with id {reviewer_id} does not have the teacher or admin role. Role is '{reviewer.role}'.",
            )
        return reviewer

    async def generate_remediation_for_finding(
        self, db: Session, finding_id: int, generator_name: Optional[str] = None
    ) -> RemediationRunDetailRead:
        """
        Generates targeted follow-up practice items for a teacher-accepted evaluation finding.
        Guarantees:
        - Only teacher-accepted findings are eligible.
        - Rejects pending, rejected, needs_revision, and insufficient_evidence findings.
        - Preserves strict provenance to source finding and evaluation run.
        - Idempotent: returns existing run if already generated for this finding/generator.
        - Never mutates source finding, original question, or student answer.
        """
        finding = db.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation finding with id {finding_id} not found.",
            )

        # 1. Eligibility Check: Must be teacher-accepted
        if finding.review_status != FindingReviewStatus.ACCEPTED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Remediation practice can only be generated from teacher-accepted evaluation findings. "
                    f"Current review status is '{finding.review_status}'."
                ),
            )

        # 2. Eligibility Check: Category cannot be insufficient evidence
        if finding.category == FindingCategory.INSUFFICIENT_EVIDENCE.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Cannot generate remediation practice for an insufficient_evidence finding.",
            )

        # 3. Retrieve context
        eval_run = db.query(EvaluationRun).filter(EvaluationRun.id == finding.run_id).first()
        if not eval_run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source evaluation run with id {finding.run_id} not found.",
            )

        question = db.query(Question).filter(Question.id == eval_run.question_id).first()
        topic = (
            db.query(LearningTopic).filter(LearningTopic.id == finding.topic_id).first()
            if finding.topic_id
            else None
        )

        generator = get_remediation_generator(generator_name)
        active_generator_name = generator.name

        # 4. Idempotency Check: Existing run for finding and generator
        existing_run = remediation_repository.get_run_by_finding_and_generator(
            db=db, finding_id=finding.id, generator_name=active_generator_name
        )
        if existing_run and existing_run.status in (
            RemediationRunStatus.COMPLETED.value,
            RemediationRunStatus.INSUFFICIENT_CONTEXT.value,
        ):
            logger.info(
                f"Returning existing idempotent remediation run {existing_run.id} for finding {finding_id}."
            )
            return RemediationRunDetailRead.model_validate(existing_run)

        # 5. Create or reuse run record
        if not existing_run:
            run = remediation_repository.create_run(
                db=db,
                finding_id=finding.id,
                evaluation_run_id=eval_run.id,
                generator_name=active_generator_name,
                status=RemediationRunStatus.PENDING,
            )
        else:
            run = existing_run

        # 6. Prepare grounded input (reading through correction resolver)
        resolved_concept = resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT) or finding.concept_name
        resolved_evidence = resolve_finding_field(finding, CorrectionFieldName.EVIDENCE_EXCERPT) or finding.evidence_excerpt

        input_data = RemediationInput(
            finding_id=finding.id,
            finding_category=FindingCategory(finding.category),
            concept_name=resolved_concept,
            evidence_excerpt=resolved_evidence,
            rationale=finding.rationale,
            question_prompt=question.prompt if question else "",
            rubric=question.rubric if question else None,
            expected_answer=question.expected_answer if question else None,
            topic_name=topic.name if topic else None,
            topic_description=topic.description if topic else None,
        )

        # 7. Execute generator
        try:
            result = await generator.generate_practice(input_data)
        except Exception as exc:
            logger.error(f"Remediation generator failed for finding {finding_id}: {exc}")
            remediation_repository.update_run_status(
                db=db,
                run_id=run.id,
                status=RemediationRunStatus.FAILED,
                error_message="Remediation generator encountered an internal execution error.",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Remediation question generation failed unexpectedly.",
            )

        # 8. Persist results
        remediation_repository.update_run_status(
            db=db,
            run_id=run.id,
            status=result.status,
            error_message=result.error_message,
        )

        if result.status == RemediationRunStatus.COMPLETED:
            for item_data in result.items:
                remediation_repository.create_item(
                    db=db,
                    run_id=run.id,
                    finding_id=finding.id,
                    item_data=item_data,
                )

        refreshed_run = remediation_repository.get_run_by_id(db, run.id)
        logger.info(
            f"Successfully processed remediation run {run.id} with status '{result.status.value}' "
            f"and {len(result.items)} practice items."
        )
        return RemediationRunDetailRead.model_validate(refreshed_run)

    def get_run_by_id(self, db: Session, run_id: int) -> RemediationRunDetailRead:
        """Retrieves a remediation run with its generated items and provenance."""
        run = remediation_repository.get_run_by_id(db=db, run_id=run_id)
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Remediation run with id {run_id} not found.",
            )
        return RemediationRunDetailRead.model_validate(run)

    def get_items_by_finding(
        self, db: Session, finding_id: int
    ) -> List[RemediationItemTeacherRead]:
        """Lists all practice items for a specific evaluation finding."""
        finding = db.query(EvaluationFinding).filter(EvaluationFinding.id == finding_id).first()
        if not finding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation finding with id {finding_id} not found.",
            )
        items = remediation_repository.get_items_by_finding(db=db, finding_id=finding_id)
        return [RemediationItemTeacherRead.model_validate(item) for item in items]

    def get_items_by_submission(
        self, db: Session, submission_id: int
    ) -> List[RemediationItemTeacherRead]:
        """Lists all practice items for an entire submission across all findings."""
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with id {submission_id} not found.",
            )
        items = remediation_repository.get_items_by_submission(db=db, submission_id=submission_id)
        return [RemediationItemTeacherRead.model_validate(item) for item in items]

    def get_item_by_id(self, db: Session, item_id: int) -> RemediationItemTeacherRead:
        """Retrieves a single practice item by ID."""
        item = remediation_repository.get_item_by_id(db=db, item_id=item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Remediation practice item with id {item_id} not found.",
            )
        return RemediationItemTeacherRead.model_validate(item)

    def review_practice_item(
        self, db: Session, item_id: int, reviewer_id: int, request: PracticeItemReviewRequest
    ) -> PracticeItemReviewResponse:
        """
        Allows a teacher to review, approve, edit, or reject a generated practice item.
        Guarantees:
        - Validates reviewer exists and has teacher or admin role.
        - Enforces state machine transitions.
        - Preserves original generated question text, storing edits in dedicated fields.
        - Retains full immutable audit trail in remediation_item_audits.
        """
        item = remediation_repository.get_item_by_id(db=db, item_id=item_id)
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Remediation practice item with id {item_id} not found.",
            )

        reviewer = self._validate_reviewer(db, reviewer_id)

        # Determine target state
        if request.action == PracticeItemReviewAction.APPROVE:
            target_status = PracticeItemReviewStatus.APPROVED
            edited_question = None
            edited_answer = None
        elif request.action == PracticeItemReviewAction.REJECT:
            target_status = PracticeItemReviewStatus.REJECTED
            edited_question = None
            edited_answer = None
        elif request.action == PracticeItemReviewAction.EDIT:
            target_status = PracticeItemReviewStatus.EDITED
            if not request.edited_question_text or not request.edited_question_text.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Field 'edited_question_text' cannot be empty when review action is 'edit'.",
                )
            edited_question = request.edited_question_text.strip()
            edited_answer = request.edited_answer_key.strip() if request.edited_answer_key else None
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unsupported review action '{request.action}'.",
            )

        # State transition validation
        previous_status = item.review_status
        try:
            validate_practice_item_transition(previous_status, target_status)
        except InvalidStateTransitionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(err),
            )

        # Update item
        updated_item = remediation_repository.update_item_review(
            db=db,
            item=item,
            new_status=target_status,
            reviewer_id=reviewer.id,
            review_notes=request.review_notes,
            edited_question_text=edited_question,
            edited_answer_key=edited_answer,
        )

        # Create audit entry
        audit = remediation_repository.create_item_audit(
            db=db,
            item_id=item.id,
            reviewer_id=reviewer.id,
            action=request.action.value,
            previous_status=previous_status,
            new_status=target_status.value,
            edited_question_text=edited_question,
            edited_answer_key=edited_answer,
            review_notes=request.review_notes,
        )

        logger.info(
            f"Teacher {reviewer.id} reviewed practice item {item.id} -> action='{request.action.value}', "
            f"new_status='{target_status.value}'"
        )
        return PracticeItemReviewResponse(
            item=RemediationItemTeacherRead.model_validate(updated_item),
            audit=RemediationItemAuditRead.model_validate(audit),
        )


remediation_service = RemediationService()
