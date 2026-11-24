from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.user import User
from app.schemas.assessment import AssessmentCreate, AssessmentUpdate


class AssessmentRepository:
    def get_by_id(self, db: Session, assessment_id: int) -> Optional[Assessment]:
        return db.query(Assessment).filter(Assessment.id == assessment_id).first()

    def get_multi(self, db: Session, limit: int = 20, offset: int = 0) -> Tuple[List[Assessment], int]:
        total = db.query(func.count(Assessment.id)).scalar() or 0
        items = db.query(Assessment).order_by(Assessment.id.asc()).offset(offset).limit(limit).all()
        return items, total

    def user_exists(self, db: Session, user_id: int) -> bool:
        return db.query(User.id).filter(User.id == user_id).first() is not None

    def create(self, db: Session, obj_in: AssessmentCreate, created_by: int) -> Assessment:
        db_obj = Assessment(
            title=obj_in.title,
            description=obj_in.description,
            created_by=created_by,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Assessment, obj_in: AssessmentUpdate) -> Assessment:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, db_obj: Assessment) -> None:
        db.delete(db_obj)
        db.commit()


assessment_repository = AssessmentRepository()
