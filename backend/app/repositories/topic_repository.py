from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.topic import LearningTopic
from app.models.assessment import Question
from app.schemas.topic import LearningTopicCreate, LearningTopicUpdate


class TopicRepository:
    def get_by_id(self, db: Session, topic_id: int) -> Optional[LearningTopic]:
        return db.query(LearningTopic).filter(LearningTopic.id == topic_id).first()

    def get_multi(self, db: Session, limit: int = 20, offset: int = 0) -> Tuple[List[LearningTopic], int]:
        total = db.query(func.count(LearningTopic.id)).scalar() or 0
        items = db.query(LearningTopic).order_by(LearningTopic.id.asc()).offset(offset).limit(limit).all()
        return items, total

    def create(self, db: Session, obj_in: LearningTopicCreate) -> LearningTopic:
        db_obj = LearningTopic(
            name=obj_in.name,
            description=obj_in.description,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: LearningTopic, obj_in: LearningTopicUpdate) -> LearningTopic:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def count_referencing_questions(self, db: Session, topic_id: int) -> int:
        return db.query(func.count(Question.id)).filter(Question.topic_id == topic_id).scalar() or 0

    def delete(self, db: Session, db_obj: LearningTopic) -> None:
        db.delete(db_obj)
        db.commit()


topic_repository = TopicRepository()
