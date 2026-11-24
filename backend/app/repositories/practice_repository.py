from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.enums import PracticeSessionStatus, validate_practice_session_transition
from app.models.practice import PracticeResponse, PracticeSession


class PracticeRepository:
    """Data access repository for student practice sessions and responses."""

    @classmethod
    def create_session(
        cls,
        db: Session,
        *,
        student_id: int,
        submission_id: int,
        total_items: int,
    ) -> PracticeSession:
        session = PracticeSession(
            student_id=student_id,
            submission_id=submission_id,
            status=PracticeSessionStatus.ACTIVE.value,
            total_items=total_items,
            completed_items=0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @classmethod
    def get_session_by_id(cls, db: Session, session_id: int) -> Optional[PracticeSession]:
        return db.query(PracticeSession).filter(PracticeSession.id == session_id).first()

    @classmethod
    def get_active_session_for_submission(
        cls, db: Session, *, student_id: int, submission_id: int
    ) -> Optional[PracticeSession]:
        return (
            db.query(PracticeSession)
            .filter(
                PracticeSession.student_id == student_id,
                PracticeSession.submission_id == submission_id,
                PracticeSession.status == PracticeSessionStatus.ACTIVE.value,
            )
            .order_by(PracticeSession.id.desc())
            .first()
        )

    @classmethod
    def list_sessions_for_submission(
        cls, db: Session, *, submission_id: int, student_id: Optional[int] = None
    ) -> List[PracticeSession]:
        query = db.query(PracticeSession).filter(PracticeSession.submission_id == submission_id)
        if student_id is not None:
            query = query.filter(PracticeSession.student_id == student_id)
        return query.order_by(PracticeSession.id.desc()).all()

    @classmethod
    def list_sessions_for_student(
        cls, db: Session, *, student_id: int
    ) -> List[PracticeSession]:
        return (
            db.query(PracticeSession)
            .filter(PracticeSession.student_id == student_id)
            .order_by(PracticeSession.id.desc())
            .all()
        )

    @classmethod
    def update_session_status(
        cls,
        db: Session,
        *,
        session: PracticeSession,
        new_status: PracticeSessionStatus,
        completed_at: Optional[datetime] = None,
    ) -> PracticeSession:
        validate_practice_session_transition(session.status, new_status)
        session.status = new_status.value
        if completed_at is not None:
            session.completed_at = completed_at
        db.commit()
        db.refresh(session)
        return session

    @classmethod
    def increment_completed_items(
        cls, db: Session, *, session: PracticeSession
    ) -> PracticeSession:
        session.completed_items += 1
        if session.completed_items >= session.total_items and session.status == PracticeSessionStatus.ACTIVE.value:
            session.status = PracticeSessionStatus.COMPLETED.value
            session.completed_at = datetime.now()
        db.commit()
        db.refresh(session)
        return session

    @classmethod
    def create_response(
        cls,
        db: Session,
        *,
        session_id: int,
        remediation_item_id: int,
        finding_id: int,
        evaluation_run_id: int,
        student_answer: str,
        is_correct: bool,
        score: float,
        feedback: Optional[str] = None,
    ) -> PracticeResponse:
        response = PracticeResponse(
            session_id=session_id,
            remediation_item_id=remediation_item_id,
            finding_id=finding_id,
            evaluation_run_id=evaluation_run_id,
            student_answer=student_answer,
            is_correct=is_correct,
            score=score,
            feedback=feedback,
        )
        db.add(response)
        db.commit()
        db.refresh(response)
        return response

    @classmethod
    def get_response(
        cls, db: Session, *, session_id: int, remediation_item_id: int
    ) -> Optional[PracticeResponse]:
        return (
            db.query(PracticeResponse)
            .filter(
                PracticeResponse.session_id == session_id,
                PracticeResponse.remediation_item_id == remediation_item_id,
            )
            .first()
        )

    @classmethod
    def get_responses_for_session(
        cls, db: Session, *, session_id: int
    ) -> List[PracticeResponse]:
        return (
            db.query(PracticeResponse)
            .filter(PracticeResponse.session_id == session_id)
            .order_by(PracticeResponse.id.asc())
            .all()
        )


practice_repository = PracticeRepository()
