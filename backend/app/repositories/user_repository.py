from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    @classmethod
    def get_by_id(cls, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @classmethod
    def get_by_email(cls, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email.lower().strip()).first()

    @classmethod
    def create(
        cls,
        db: Session,
        obj_in: UserCreate,
        hashed_password: Optional[str] = None,
    ) -> User:
        final_hash = hashed_password
        if not final_hash and getattr(obj_in, "password", None):
            final_hash = hash_password(obj_in.password)

        role_value = obj_in.role.value if hasattr(obj_in.role, "value") else str(obj_in.role)

        db_user = User(
            full_name=obj_in.full_name,
            email=obj_in.email.lower().strip(),
            role=role_value,
            hashed_password=final_hash,
            is_active=obj_in.is_active,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @classmethod
    def authenticate(
        cls, db: Session, *, email: str, password: str
    ) -> Optional[User]:
        user = cls.get_by_email(db, email=email)
        if not user:
            return None
        if not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @classmethod
    def update(cls, db: Session, *, db_user: User, obj_in: UserUpdate) -> User:
        update_data = obj_in.model_dump(exclude_unset=True)
        if "role" in update_data and update_data["role"]:
            role_val = update_data["role"]
            update_data["role"] = role_val.value if hasattr(role_val, "value") else str(role_val)

        for field, value in update_data.items():
            setattr(db_user, field, value)

        db.commit()
        db.refresh(db_user)
        return db_user


user_repository = UserRepository()
