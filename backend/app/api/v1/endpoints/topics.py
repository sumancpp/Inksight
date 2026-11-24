from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_teacher
from app.core.database import get_db
from app.models.user import User
from app.repositories.topic_repository import topic_repository
from app.schemas.common import PaginatedResponse
from app.schemas.topic import LearningTopicCreate, LearningTopicRead, LearningTopicUpdate

router = APIRouter()


@router.post(
    "",
    response_model=LearningTopicRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new learning topic",
)
def create_topic(
    topic_in: LearningTopicCreate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> LearningTopicRead:
    return topic_repository.create(db=db, obj_in=topic_in)


@router.get(
    "",
    response_model=PaginatedResponse[LearningTopicRead],
    summary="List learning topics with pagination",
)
def list_topics(
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[LearningTopicRead]:
    items, total = topic_repository.get_multi(db=db, limit=limit, offset=offset)
    return PaginatedResponse[LearningTopicRead](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{topic_id}",
    response_model=LearningTopicRead,
    summary="Get a learning topic by ID",
)
def get_topic(
    topic_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> LearningTopicRead:
    topic = topic_repository.get_by_id(db=db, topic_id=topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning topic with id {topic_id} not found.",
        )
    return topic


@router.patch(
    "/{topic_id}",
    response_model=LearningTopicRead,
    summary="Update a learning topic",
)
def update_topic(
    topic_id: int,
    topic_in: LearningTopicUpdate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> LearningTopicRead:
    topic = topic_repository.get_by_id(db=db, topic_id=topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning topic with id {topic_id} not found.",
        )
    return topic_repository.update(db=db, db_obj=topic, obj_in=topic_in)


@router.delete(
    "/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a learning topic",
)
def delete_topic(
    topic_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    topic = topic_repository.get_by_id(db=db, topic_id=topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning topic with id {topic_id} not found.",
        )

    referencing_count = topic_repository.count_referencing_questions(db=db, topic_id=topic_id)
    if referencing_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Topic is referenced by {referencing_count} question(s) and cannot be deleted.",
        )

    topic_repository.delete(db=db, db_obj=topic)
