from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import SubmissionStatus
from app.models.submission import QuestionAnswer, Submission
from app.models.user import User
from app.schemas.submission import (
    QuestionAnswerCreate,
    QuestionAnswerUpdate,
    SubmissionCreate,
    SubmissionUpdate,
)


class SubmissionRepository:
    def get_by_id(self, db: Session, submission_id: int) -> Optional[Submission]:
        return db.query(Submission).filter(Submission.id == submission_id).first()

    def get_multi_by_assessment(
        self, db: Session, assessment_id: int, limit: int = 20, offset: int = 0, student_id: Optional[int] = None
    ) -> Tuple[List[Submission], int]:
        query = db.query(Submission).filter(Submission.assessment_id == assessment_id)
        if student_id is not None:
            query = query.filter(Submission.student_id == student_id)
        total = query.with_entities(func.count(Submission.id)).scalar() or 0
        items = (
            query
            .order_by(Submission.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def user_exists(self, db: Session, user_id: int) -> bool:
        return db.query(User.id).filter(User.id == user_id).first() is not None

    def create_submission(self, db: Session, assessment_id: int, obj_in: SubmissionCreate, student_id: int) -> Submission:
        status_val = (
            obj_in.status.value
            if hasattr(obj_in.status, "value")
            else str(obj_in.status)
        )
        submitted_at = None
        if status_val == SubmissionStatus.SUBMITTED.value:
            submitted_at = datetime.now(timezone.utc)

        db_obj = Submission(
            assessment_id=assessment_id,
            student_id=student_id,
            status=status_val,
            submitted_at=submitted_at,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_submission(self, db: Session, db_obj: Submission, obj_in: SubmissionUpdate) -> Submission:
        update_data = obj_in.model_dump(exclude_unset=True)
        if "status" in update_data and update_data["status"] is not None:
            status_enum = update_data["status"]
            status_val = status_enum.value if hasattr(status_enum, "value") else str(status_enum)
            update_data["status"] = status_val
            if status_val == SubmissionStatus.SUBMITTED.value and not update_data.get("submitted_at") and not db_obj.submitted_at:
                update_data["submitted_at"] = datetime.now(timezone.utc)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_answer_by_id(self, db: Session, answer_id: int) -> Optional[QuestionAnswer]:
        return db.query(QuestionAnswer).filter(QuestionAnswer.id == answer_id).first()

    def get_answer_by_submission_and_question(
        self, db: Session, submission_id: int, question_id: int
    ) -> Optional[QuestionAnswer]:
        return (
            db.query(QuestionAnswer)
            .filter(
                QuestionAnswer.submission_id == submission_id,
                QuestionAnswer.question_id == question_id,
            )
            .first()
        )

    def get_answers_for_submission(
        self, db: Session, submission_id: int, limit: int = 50, offset: int = 0
    ) -> Tuple[List[QuestionAnswer], int]:
        total = (
            db.query(func.count(QuestionAnswer.id))
            .filter(QuestionAnswer.submission_id == submission_id)
            .scalar()
            or 0
        )
        items = (
            db.query(QuestionAnswer)
            .filter(QuestionAnswer.submission_id == submission_id)
            .order_by(QuestionAnswer.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def create_answer(
        self, db: Session, submission_id: int, obj_in: QuestionAnswerCreate
    ) -> QuestionAnswer:
        db_obj = QuestionAnswer(
            submission_id=submission_id,
            question_id=obj_in.question_id,
            answer_text=obj_in.answer_text,
            awarded_marks=obj_in.awarded_marks,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_answer(
        self, db: Session, db_obj: QuestionAnswer, obj_in: QuestionAnswerUpdate
    ) -> QuestionAnswer:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


submission_repository = SubmissionRepository()
