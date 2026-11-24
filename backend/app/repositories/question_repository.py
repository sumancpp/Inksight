from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.assessment import Question
from app.schemas.question import QuestionCreate, QuestionUpdate


class QuestionRepository:
    def get_by_id(self, db: Session, question_id: int) -> Optional[Question]:
        return db.query(Question).filter(Question.id == question_id).first()

    def get_multi_by_assessment(
        self, db: Session, assessment_id: int, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Question], int]:
        total = db.query(func.count(Question.id)).filter(Question.assessment_id == assessment_id).scalar() or 0
        items = (
            db.query(Question)
            .filter(Question.assessment_id == assessment_id)
            .order_by(Question.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def create(self, db: Session, assessment_id: int, obj_in: QuestionCreate) -> Question:
        question_type_val = (
            obj_in.question_type.value
            if hasattr(obj_in.question_type, "value")
            else str(obj_in.question_type)
        )
        db_obj = Question(
            assessment_id=assessment_id,
            topic_id=obj_in.topic_id,
            prompt=obj_in.prompt,
            question_type=question_type_val,
            marks=obj_in.marks,
            rubric=obj_in.rubric,
            expected_answer=obj_in.expected_answer,
            is_reference_proposed=getattr(obj_in, "is_reference_proposed", False),
            reference_status=getattr(obj_in, "reference_status", "approved"),
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


    def update(self, db: Session, db_obj: Question, obj_in: QuestionUpdate) -> Question:
        update_data = obj_in.model_dump(exclude_unset=True)
        if "question_type" in update_data and update_data["question_type"] is not None:
            qt = update_data["question_type"]
            update_data["question_type"] = qt.value if hasattr(qt, "value") else str(qt)

        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, db_obj: Question) -> None:
        db.delete(db_obj)
        db.commit()


question_repository = QuestionRepository()
