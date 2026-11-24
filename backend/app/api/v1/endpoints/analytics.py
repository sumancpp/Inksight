from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.core.database import get_db
from app.models.user import User
from app.schemas.cluster import MisconceptionClusterResponse
from app.services.cluster_service import cluster_service

router = APIRouter()


@router.get(
    "/analytics/assessments/{assessment_id}/misconception-clusters",
    response_model=MisconceptionClusterResponse,
    status_code=status.HTTP_200_OK,
    summary="Get class-level misconception clusters for an assessment",
    description=(
        "Aggregates accepted and acknowledged evaluation findings by linked concept. "
        "Enforces the minimum 2 distinct students threshold for clusters. "
        "Single-occurrence misconceptions are isolated. Correct findings and unacknowledged "
        "low-confidence findings are strictly excluded."
    ),
)
def get_misconception_clusters(
    assessment_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> MisconceptionClusterResponse:
    return cluster_service.get_misconception_clusters(db=db, assessment_id=assessment_id)


# Backward-compatible alias under /evaluations
@router.get(
    "/evaluations/assessments/{assessment_id}/misconception-clusters",
    response_model=MisconceptionClusterResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_misconception_clusters_eval_alias(
    assessment_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> MisconceptionClusterResponse:
    return cluster_service.get_misconception_clusters(db=db, assessment_id=assessment_id)

