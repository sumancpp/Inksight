from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_teacher
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.question_repository import question_repository
from app.repositories.topic_repository import topic_repository
from app.schemas.question import QuestionRead, QuestionUpdate

router = APIRouter()


@router.get(
    "/{question_id}",
    response_model=QuestionRead,
    summary="Get a question by ID",
)
def get_question(
    question_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> QuestionRead:
    question = question_repository.get_by_id(db=db, question_id=question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with id {question_id} not found.",
        )
    return question


@router.patch(
    "/{question_id}",
    response_model=QuestionRead,
    summary="Update a question",
)
def update_question(
    question_id: int,
    question_in: QuestionUpdate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> QuestionRead:
    question = question_repository.get_by_id(db=db, question_id=question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with id {question_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and question.assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this question",
        )

    # If updating topic_id, verify the target topic exists
    if question_in.topic_id is not None:
        topic = topic_repository.get_by_id(db=db, topic_id=question_in.topic_id)
        if not topic:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Learning topic with id {question_in.topic_id} not found.",
            )

    return question_repository.update(db=db, db_obj=question, obj_in=question_in)


@router.delete(
    "/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a question",
)
def delete_question(
    question_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    question = question_repository.get_by_id(db=db, question_id=question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with id {question_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and question.assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this question",
        )

    question_repository.delete(db=db, db_obj=question)
