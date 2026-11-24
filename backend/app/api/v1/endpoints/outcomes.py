from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_teacher
from app.core.database import get_db
from app.models.user import User
from app.schemas.outcome import (
    InterventionOutcomesSummary,
    StudentProgressReportRead,
)
from app.services.outcome_service import outcome_service

router = APIRouter()


@router.get(
    "/submissions/{submission_id}/intervention-outcomes",
    response_model=InterventionOutcomesSummary,
    status_code=status.HTTP_200_OK,
    summary="Get teacher-facing intervention outcomes for a submission",
    description=(
        "Compares initial diagnostic findings with follow-up practice evidence for a submission. "
        "Surfaces support given, student responses, outcome verdict (improved, uncertain, persisting gap), "
        "uncertainty level, and recommended instructor action. Teacher/admin only."
    ),
)
def get_submission_intervention_outcomes(
    submission_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> InterventionOutcomesSummary:
    return outcome_service.get_submission_intervention_outcomes(db=db, submission_id=submission_id)


@router.get(
    "/assessments/{assessment_id}/intervention-outcomes",
    response_model=InterventionOutcomesSummary,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated intervention outcomes across an assessment",
    description=(
        "Aggregates intervention outcomes across all student submissions for an assessment. "
        "Teacher/admin only."
    ),
)
def get_assessment_intervention_outcomes(
    assessment_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> InterventionOutcomesSummary:
    return outcome_service.get_assessment_intervention_outcomes(db=db, assessment_id=assessment_id)


@router.get(
    "/submissions/{submission_id}/student-progress",
    response_model=StudentProgressReportRead,
    status_code=status.HTTP_200_OK,
    summary="Get student-facing topic-wise progress and learning loop report",
    description=(
        "Surfaces student-safe progress across evaluated concepts, prior baseline gaps, "
        "follow-up exercise evidence, remaining gaps, and evidence-based recommended next steps. "
        "STRICTLY EXCLUDES teacher-only answer keys, rationales, and review comments. "
        "Authenticated students can only access their own submissions; teachers/admins can view any."
    ),
)
def get_student_progress_report(
    submission_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> StudentProgressReportRead:
    return outcome_service.get_student_progress_report(
        db=db, submission_id=submission_id, current_user=current_user
    )

