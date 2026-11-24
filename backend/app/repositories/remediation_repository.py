from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.enums import PracticeItemReviewStatus, RemediationRunStatus
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.remediation import RemediationItem, RemediationItemAudit, RemediationRun
from app.schemas.remediation import PracticeItemOutput


class RemediationRepository:
    def get_run_by_id(self, db: Session, run_id: int) -> Optional[RemediationRun]:
        return db.query(RemediationRun).filter(RemediationRun.id == run_id).first()

    def get_run_by_finding_and_generator(
        self, db: Session, finding_id: int, generator_name: str
    ) -> Optional[RemediationRun]:
        return (
            db.query(RemediationRun)
            .filter(
                RemediationRun.finding_id == finding_id,
                RemediationRun.generator_name == generator_name,
            )
            .first()
        )

    def get_runs_by_finding(self, db: Session, finding_id: int) -> List[RemediationRun]:
        return (
            db.query(RemediationRun)
            .filter(RemediationRun.finding_id == finding_id)
            .order_by(RemediationRun.id.desc())
            .all()
        )

    def create_run(
        self,
        db: Session,
        finding_id: int,
        evaluation_run_id: int,
        generator_name: str,
        status: RemediationRunStatus = RemediationRunStatus.PENDING,
        error_message: Optional[str] = None,
    ) -> RemediationRun:
        run = RemediationRun(
            finding_id=finding_id,
            evaluation_run_id=evaluation_run_id,
            generator_name=generator_name,
            status=status.value,
            error_message=error_message,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def update_run_status(
        self,
        db: Session,
        run_id: int,
        status: RemediationRunStatus,
        error_message: Optional[str] = None,
    ) -> RemediationRun:
        run = self.get_run_by_id(db, run_id)
        if run:
            run.status = status.value
            run.error_message = error_message
            db.commit()
            db.refresh(run)
        return run

    def create_item(
        self,
        db: Session,
        run_id: int,
        finding_id: int,
        item_data: PracticeItemOutput,
    ) -> RemediationItem:
        item = RemediationItem(
            run_id=run_id,
            finding_id=finding_id,
            target_concept=item_data.target_concept,
            question_text=item_data.question_text,
            question_type=item_data.question_type.value,
            options=item_data.options,
            teacher_answer_key=item_data.teacher_answer_key,
            teacher_rationale=item_data.teacher_rationale,
            difficulty=item_data.difficulty,
            uncertainty_note=item_data.uncertainty_note,
            review_status=PracticeItemReviewStatus.PENDING_REVIEW.value,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def get_item_by_id(self, db: Session, item_id: int) -> Optional[RemediationItem]:
        return db.query(RemediationItem).filter(RemediationItem.id == item_id).first()

    def get_items_by_finding(self, db: Session, finding_id: int) -> List[RemediationItem]:
        return (
            db.query(RemediationItem)
            .filter(RemediationItem.finding_id == finding_id)
            .order_by(RemediationItem.id.asc())
            .all()
        )

    def get_items_by_submission(
        self, db: Session, submission_id: int
    ) -> List[RemediationItem]:
        return (
            db.query(RemediationItem)
            .join(EvaluationFinding, RemediationItem.finding_id == EvaluationFinding.id)
            .join(EvaluationRun, EvaluationFinding.run_id == EvaluationRun.id)
            .filter(EvaluationRun.submission_id == submission_id)
            .order_by(RemediationItem.id.asc())
            .all()
        )

    def update_item_review(
        self,
        db: Session,
        item: RemediationItem,
        new_status: PracticeItemReviewStatus,
        reviewer_id: int,
        review_notes: Optional[str] = None,
        edited_question_text: Optional[str] = None,
        edited_answer_key: Optional[str] = None,
    ) -> RemediationItem:
        item.review_status = new_status.value
        item.reviewed_by = reviewer_id
        item.reviewed_at = datetime.now(timezone.utc)
        item.review_notes = review_notes
        if edited_question_text is not None:
            item.edited_question_text = edited_question_text
        if edited_answer_key is not None:
            item.edited_answer_key = edited_answer_key
        db.commit()
        db.refresh(item)
        return item

    def create_item_audit(
        self,
        db: Session,
        item_id: int,
        reviewer_id: int,
        action: str,
        previous_status: Optional[str],
        new_status: str,
        edited_question_text: Optional[str] = None,
        edited_answer_key: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> RemediationItemAudit:
        audit = RemediationItemAudit(
            item_id=item_id,
            reviewer_id=reviewer_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            edited_question_text=edited_question_text,
            edited_answer_key=edited_answer_key,
            review_notes=review_notes,
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit


remediation_repository = RemediationRepository()
