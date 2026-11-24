from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.enums import ProposalStatus, ReviewAction
from app.models.matching import ProposedAnswer, TeacherReview


class MatchingRepository:
    def get_proposal_by_id(self, db: Session, proposal_id: int) -> Optional[ProposedAnswer]:
        return db.query(ProposedAnswer).filter(ProposedAnswer.id == proposal_id).first()

    def get_proposals_by_submission(
        self, db: Session, submission_id: int
    ) -> List[ProposedAnswer]:
        return (
            db.query(ProposedAnswer)
            .filter(ProposedAnswer.submission_id == submission_id)
            .order_by(ProposedAnswer.question_id.asc().nulls_last(), ProposedAnswer.id.asc())
            .all()
        )

    def get_proposals_by_upload(self, db: Session, upload_id: int) -> List[ProposedAnswer]:
        return (
            db.query(ProposedAnswer)
            .filter(ProposedAnswer.upload_id == upload_id)
            .order_by(ProposedAnswer.question_id.asc().nulls_last(), ProposedAnswer.id.asc())
            .all()
        )

    def get_proposal_by_upload_and_segment(
        self, db: Session, upload_id: int, segment_id: int
    ) -> Optional[ProposedAnswer]:
        return (
            db.query(ProposedAnswer)
            .filter(
                ProposedAnswer.upload_id == upload_id,
                ProposedAnswer.segment_id == segment_id,
            )
            .first()
        )

    def upsert_proposal(
        self,
        db: Session,
        submission_id: int,
        upload_id: int,
        ocr_extraction_id: int,
        question_id: Optional[int],
        segment_id: Optional[int],
        proposed_text: str,
        confidence: Optional[float],
        status: ProposalStatus,
        rejection_reason: Optional[str] = None,
    ) -> ProposedAnswer:
        existing: Optional[ProposedAnswer] = None
        if segment_id is not None:
            existing = self.get_proposal_by_upload_and_segment(
                db=db, upload_id=upload_id, segment_id=segment_id
            )

        status_val = status.value if hasattr(status, "value") else str(status)

        if existing:
            # If already reviewed by a teacher, preserve review state
            if existing.status in [
                ProposalStatus.APPROVED.value,
                ProposalStatus.CORRECTED.value,
                ProposalStatus.REJECTED.value,
            ]:
                return existing

            existing.question_id = question_id
            existing.proposed_text = proposed_text
            existing.confidence = confidence
            existing.status = status_val
            existing.rejection_reason = rejection_reason
            db.commit()
            db.refresh(existing)
            return existing

        db_obj = ProposedAnswer(
            submission_id=submission_id,
            upload_id=upload_id,
            ocr_extraction_id=ocr_extraction_id,
            question_id=question_id,
            segment_id=segment_id,
            proposed_text=proposed_text,
            confidence=confidence,
            status=status_val,
            rejection_reason=rejection_reason,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_teacher_review(
        self,
        db: Session,
        proposal_id: int,
        submission_id: int,
        question_id: Optional[int],
        reviewer_id: int,
        action: ReviewAction,
        original_text: str,
        final_text: Optional[str],
        review_notes: Optional[str] = None,
    ) -> TeacherReview:
        action_val = action.value if hasattr(action, "value") else str(action)
        review_record = TeacherReview(
            proposal_id=proposal_id,
            submission_id=submission_id,
            question_id=question_id,
            reviewer_id=reviewer_id,
            action=action_val,
            original_text=original_text,
            final_text=final_text,
            review_notes=review_notes,
        )
        db.add(review_record)
        db.commit()
        db.refresh(review_record)
        return review_record


matching_repository = MatchingRepository()
