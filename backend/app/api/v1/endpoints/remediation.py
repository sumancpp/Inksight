from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_teacher
from app.core.database import get_db
from app.models.user import User
from app.schemas.remediation import (
    PracticeItemReviewRequest,
    PracticeItemReviewResponse,
    RemediationItemTeacherRead,
    RemediationRunDetailRead,
)
from app.services.remediation_service import remediation_service

router = APIRouter()


@router.post(
    "/findings/{finding_id}/remediation/generate",
    response_model=RemediationRunDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Trigger targeted remediation generation for an evaluation finding",
    description=(
        "Generates targeted practice items for a teacher-accepted evaluation finding. "
        "Strictly requires the finding to have review_status='accepted'. "
        "Pending, rejected, needs_revision, and insufficient_evidence findings are rejected. "
        "Gated to teachers and admins only."
    ),
)
async def generate_remediation_for_finding(
    finding_id: int,
    generator_name: Optional[str] = Query(None, description="Optional generator override (defaults to configured mock)"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return await remediation_service.generate_remediation_for_finding(
        db=db, finding_id=finding_id, generator_name=generator_name
    )


@router.get(
    "/findings/{finding_id}/remediations",
    response_model=List[RemediationItemTeacherRead],
    status_code=status.HTTP_200_OK,
    summary="List generated practice items for an evaluation finding",
    description="Lists all generated practice items associated with an evaluation finding (teacher review view).",
)
def get_items_for_finding(
    finding_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return remediation_service.get_items_by_finding(db=db, finding_id=finding_id)


@router.get(
    "/submissions/{submission_id}/remediations",
    response_model=List[RemediationItemTeacherRead],
    status_code=status.HTTP_200_OK,
    summary="List generated practice items for a submission",
    description="Lists all practice items generated across all evaluation findings for a student submission (teacher review view).",
)
def get_items_for_submission(
    submission_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return remediation_service.get_items_by_submission(db=db, submission_id=submission_id)


@router.get(
    "/remediations/runs/{run_id}",
    response_model=RemediationRunDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a remediation generation run by ID",
    description="Retrieves a remediation generation run with its generated practice items and audit provenance (teacher review view).",
)
def get_remediation_run_by_id(
    run_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return remediation_service.get_run_by_id(db=db, run_id=run_id)


@router.get(
    "/remediations/items/{item_id}",
    response_model=RemediationItemTeacherRead,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a single practice item by ID",
    description="Retrieves a single remediation practice item with teacher-only answer keys, rationales, and review status.",
)
def get_remediation_item_by_id(
    item_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return remediation_service.get_item_by_id(db=db, item_id=item_id)


@router.post(
    "/remediations/items/{item_id}/review",
    response_model=PracticeItemReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Review, approve, edit, or reject a generated practice item",
    description=(
        "Teacher review workflow for practice items. "
        "Allows a teacher to approve, reject, or edit the item before it is finalized. "
        "Original generated text is preserved; edits are stored in dedicated fields with audit logging."
    ),
)
def review_practice_item(
    item_id: int,
    payload: PracticeItemReviewRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return remediation_service.review_practice_item(
        db=db,
        item_id=item_id,
        reviewer_id=current_user.id,
        request=payload,
    )
