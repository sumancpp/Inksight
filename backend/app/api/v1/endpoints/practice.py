from typing import List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.practice import (
    PracticeResponseRead,
    PracticeResponseSubmit,
    PracticeSessionDetailRead,
    PracticeSessionRead,
    PracticeSessionSummary,
)
from app.services.practice_service import practice_service

router = APIRouter()


@router.post(
    "/submissions/{submission_id}/practice-sessions",
    response_model=PracticeSessionDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start or resume a student practice session",
    description=(
        "Initiates or resumes a student practice session for a submission. "
        "Delivers ONLY teacher-approved remediation practice items originating from accepted findings. "
        "Strictly excludes teacher-only keys, rationales, uncertainty notes, and internal review comments. "
        "Student identity is derived directly from the authenticated JWT."
    ),
)
def start_practice_session(
    submission_id: int,
    resume_active: bool = Query(True, description="If true, resumes existing active session for this submission"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.start_practice_session(
        db, submission_id=submission_id, current_user=current_user, resume_active=resume_active
    )


@router.get(
    "/submissions/{submission_id}/practice-sessions",
    response_model=List[PracticeSessionRead],
    status_code=status.HTTP_200_OK,
    summary="List practice sessions for a submission",
    description=(
        "Lists practice sessions for a submission. "
        "Students can only view their own sessions; teachers and admins can view all sessions for the submission."
    ),
)
def list_practice_sessions(
    submission_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.list_sessions_for_submission(
        db, submission_id=submission_id, current_user=current_user
    )


@router.get(
    "/practice-sessions/{session_id}",
    response_model=PracticeSessionDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get practice session details",
    description=(
        "Retrieves practice session metadata, approved deliverable practice items, and any submitted responses. "
        "Student caller must be the owner of the session. "
        "Never exposes teacher answer keys or internal review notes."
    ),
)
def get_practice_session(
    session_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.get_practice_session(
        db, session_id=session_id, current_user=current_user
    )


@router.post(
    "/practice-sessions/{session_id}/responses",
    response_model=PracticeResponseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an answer to a practice item",
    description=(
        "Submits a student's answer to an approved remediation practice item in an active practice session. "
        "Enforces authenticated student ownership, active session state, item approval, and single submission per item. "
        "Returns deterministic scoring and safe feedback without revealing internal teacher notes."
    ),
)
def submit_practice_response(
    session_id: int,
    request: PracticeResponseSubmit,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.submit_response(
        db, session_id=session_id, request=request, current_user=current_user
    )


@router.get(
    "/practice-sessions/{session_id}/summary",
    response_model=PracticeSessionSummary,
    status_code=status.HTTP_200_OK,
    summary="Get practice session formative evaluation summary",
    description=(
        "Compiles transparent scoring, accuracy, and concept-level evidence for a practice session. "
        "Explicitly states that scores represent formative practice evidence and does not claim certified concept mastery."
    ),
)
def get_practice_session_summary(
    session_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.get_session_summary(
        db, session_id=session_id, current_user=current_user
    )


@router.post(
    "/practice-sessions/{session_id}/complete",
    response_model=PracticeSessionRead,
    status_code=status.HTTP_200_OK,
    summary="Mark practice session as completed",
    description="Explicitly transitions an active practice session to completed.",
)
def complete_practice_session(
    session_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.complete_session(
        db, session_id=session_id, current_user=current_user
    )


@router.post(
    "/practice-sessions/{session_id}/abandon",
    response_model=PracticeSessionRead,
    status_code=status.HTTP_200_OK,
    summary="Mark practice session as abandoned",
    description="Transitions an active practice session to abandoned.",
)
def abandon_practice_session(
    session_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
):
    return practice_service.abandon_session(
        db, session_id=session_id, current_user=current_user
    )
