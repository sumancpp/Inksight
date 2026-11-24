from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_teacher
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.evaluation_repository import evaluation_repository
from app.repositories.submission_repository import submission_repository
from app.schemas.evaluation import (
    AsyncTaskAcceptedResponse,
    EvaluationRunDetailRead,
    FindingReviewRequest,
    FindingReviewResponse,
    SubmissionEvaluationSummary,
    TaskStatusResponse,
)
from app.workers.ocr_worker import dispatch_ocr_and_evaluate
from app.schemas.follow_up import (
    FollowUpApproveRequest,
    FollowUpQuestionRead,
    FollowUpRejectRequest,
)
from app.schemas.correction import FindingCorrectionCreate, FindingCorrectionRead
from app.schemas.review_queue import PendingReviewQueueResponse
from app.services.correction_service import correction_service
from app.services.evaluation_service import evaluation_service
from app.services.followup_generation_service import followup_generation_service
from app.services.review_queue_service import review_queue_service

router = APIRouter()


def _assert_submission_evaluation_access(submission, user: User) -> None:
    user_role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    if user_role == UserRole.STUDENT.value and submission.student_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access evaluation for this submission",
        )


@router.get(
    "/submissions/task-status/{task_id}",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get background Celery task status and findings for an async evaluation",
)
def get_celery_task_status(
    task_id: str,
    current_user: User = Depends(require_active_user),
) -> TaskStatusResponse:
    """
    Returns the Celery task state (PENDING, STARTED, SUCCESS, FAILURE).
    If SUCCESS, returns evaluation findings. If FAILURE, returns error message.
    """
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app

    res = AsyncResult(task_id, app=celery_app)
    state = res.state  # PENDING, STARTED, SUCCESS, FAILURE

    if state == "SUCCESS":
        result = res.result
        findings = result.get("findings") if isinstance(result, dict) else None
        return TaskStatusResponse(
            task_id=task_id,
            status="SUCCESS",
            ready=True,
            successful=True,
            result=result,
            findings=findings,
            error=None,
        )
    elif state == "FAILURE":
        err_msg = str(res.result) if res.result else "Task execution failed."
        return TaskStatusResponse(
            task_id=task_id,
            status="FAILURE",
            ready=True,
            successful=False,
            result=None,
            findings=None,
            error=err_msg,
        )
    elif state == "STARTED":
        meta = res.info if isinstance(res.info, dict) else {}
        return TaskStatusResponse(
            task_id=task_id,
            status="STARTED",
            ready=False,
            successful=None,
            result=meta,
            findings=None,
            error=None,
        )
    else:
        return TaskStatusResponse(
            task_id=task_id,
            status=state or "PENDING",
            ready=False,
            successful=None,
            result=None,
            findings=None,
            error=None,
        )


@router.post(
    "/submissions/{submission_id}/evaluate",
    response_model=Union[AsyncTaskAcceptedResponse, SubmissionEvaluationSummary],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger async AI evaluation for all teacher-approved answers in a submission",
)
async def evaluate_submission_answers(
    submission_id: int,
    sync: bool = Query(default=False, description="Run synchronously instead of via background Celery worker"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
    response: Response = None,
):
    """
    Dispatches OCR & AI evaluation to background Celery worker.
    Returns 202 Accepted with task_id.
    If sync=True, runs synchronously and returns 200 with full summary.
    """
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )
    _assert_submission_evaluation_access(submission, current_user)

    if sync:
        if response:
            response.status_code = status.HTTP_200_OK
        return await evaluation_service.evaluate_submission(db=db, submission_id=submission_id)

    task = dispatch_ocr_and_evaluate(submission_id)
    return AsyncTaskAcceptedResponse(
        task_id=task.id,
        status="ACCEPTED",
        message="Background OCR & AI evaluation task queued.",
        submission_id=submission_id,
    )


@router.post(
    "/submissions/{submission_id}/questions/{question_id}/evaluate",
    response_model=EvaluationRunDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Trigger AI evaluation for a single teacher-approved question answer",
)
async def evaluate_question_answer(
    submission_id: int,
    question_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> EvaluationRunDetailRead:
    """
    Evaluates a single question's teacher-approved answer. Teacher-only operation.
    Fails with 422 if answer is unreviewed, unapproved, or missing.
    Idempotent: returns existing run if answer text hash is identical.
    """
    return await evaluation_service.evaluate_question_answer(
        db=db, submission_id=submission_id, question_id=question_id
    )


@router.get(
    "/submissions/{submission_id}/evaluations",
    response_model=SubmissionEvaluationSummary,
    status_code=status.HTTP_200_OK,
    summary="Get all AI evaluation runs and findings for a submission",
)
def get_submission_evaluations(
    submission_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> SubmissionEvaluationSummary:
    """
    Retrieves all evaluation runs and associated conceptual findings for a submission.
    Gated so students can only view their own submission evaluations.
    """
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )
    _assert_submission_evaluation_access(submission, current_user)
    return evaluation_service.get_submission_evaluations(db=db, submission_id=submission_id)


@router.get(
    "/submissions/{submission_id}/questions/{question_id}/evaluations",
    response_model=List[EvaluationRunDetailRead],
    status_code=status.HTTP_200_OK,
    summary="Get all AI evaluation runs for a specific question answer",
)
def get_question_evaluations(
    submission_id: int,
    question_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> List[EvaluationRunDetailRead]:
    """
    Retrieves evaluation history for a specific question answer across revisions.
    Gated so students can only view their own submission evaluations.
    """
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )
    _assert_submission_evaluation_access(submission, current_user)
    return evaluation_service.get_question_evaluations(
        db=db, submission_id=submission_id, question_id=question_id
    )


@router.get(
    "/evaluations/runs/{run_id}",
    response_model=EvaluationRunDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get a single evaluation run with findings and provenance snapshot",
)
def get_evaluation_run(
    run_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> EvaluationRunDetailRead:
    """
    Retrieves a single evaluation run with its immutable answer text snapshot and findings.
    """
    run = evaluation_repository.get_run_by_id(db=db, run_id=run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation run with id {run_id} not found.",
        )
    submission = submission_repository.get_by_id(db=db, submission_id=run.submission_id)
    if submission:
        _assert_submission_evaluation_access(submission, current_user)
    return evaluation_service.get_run(db=db, run_id=run_id)


@router.post(
    "/evaluations/findings/{finding_id}/review",
    response_model=FindingReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Teacher reviews a conceptual finding (accepted, rejected, needs_revision)",
)
def review_finding(
    finding_id: int,
    payload: FindingReviewRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FindingReviewResponse:
    """
    Teacher review for a misconception or conceptual understanding finding:
    - Sets review status to accepted, rejected, or needs_revision
    - Requires reviewer to be authenticated teacher
    - Derives reviewer ID strictly from authenticated token
    - Preserves audit history with reviewer ID, timestamp, and notes
    """
    return evaluation_service.review_finding(
        db=db,
        finding_id=finding_id,
        reviewer_id=current_user.id,
        request=payload,
    )


@router.post(
    "/evaluations/findings/{finding_id}/follow-up/propose",
    response_model=FollowUpQuestionRead,
    status_code=status.HTTP_200_OK,
    summary="Generate a targeted follow-up question for an accepted misconception finding",
)
async def propose_follow_up(
    finding_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FollowUpQuestionRead:
    return await followup_generation_service.propose_follow_up(
        db=db,
        finding_id=finding_id,
        teacher_id=current_user.id,
    )


@router.post(
    "/evaluations/follow-ups/{id}/approve",
    response_model=FollowUpQuestionRead,
    status_code=status.HTTP_200_OK,
    summary="Teacher approves a proposed follow-up question",
)
def approve_follow_up(
    id: int,
    payload: FollowUpApproveRequest = FollowUpApproveRequest(),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FollowUpQuestionRead:
    return followup_generation_service.approve_follow_up(
        db=db,
        follow_up_id=id,
        teacher_id=current_user.id,
        audit_notes=payload.audit_notes,
    )


@router.post(
    "/evaluations/follow-ups/{id}/reject",
    response_model=FollowUpQuestionRead,
    status_code=status.HTTP_200_OK,
    summary="Teacher rejects a proposed follow-up question with reason",
)
def reject_follow_up(
    id: int,
    payload: FollowUpRejectRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FollowUpQuestionRead:
    return followup_generation_service.reject_follow_up(
        db=db,
        follow_up_id=id,
        teacher_id=current_user.id,
        reason=payload.reason,
    )


@router.get(
    "/evaluations/findings/{finding_id}/follow-ups",
    response_model=List[FollowUpQuestionRead],
    status_code=status.HTTP_200_OK,
    summary="List follow-up questions for a finding",
)
def get_follow_ups(
    finding_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> List[FollowUpQuestionRead]:
    return followup_generation_service.get_follow_ups_for_finding(
        db=db,
        finding_id=finding_id,
    )


@router.post(
    "/evaluations/findings/{id}/corrections",
    response_model=FindingCorrectionRead,
    status_code=status.HTTP_200_OK,
    summary="Teacher applies an authoritative correction to an AI evaluation finding field",
)
def apply_correction(
    id: int,
    payload: FindingCorrectionCreate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FindingCorrectionRead:
    return correction_service.apply_correction(
        db=db,
        finding_id=id,
        field_name=payload.field_name,
        new_value=payload.corrected_value,
        reason=payload.correction_reason,
        teacher_id=current_user.id,
    )


@router.post(
    "/evaluations/findings/{id}/corrections/{corr_id}/revert",
    response_model=FindingCorrectionRead,
    status_code=status.HTTP_200_OK,
    summary="Teacher reverts a correction back to the original AI value",
)
def revert_correction(
    id: int,
    corr_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> FindingCorrectionRead:
    return correction_service.revert_to_ai(
        db=db,
        finding_id=id,
        correction_id=corr_id,
        teacher_id=current_user.id,
    )


@router.get(
    "/evaluations/findings/{id}/corrections",
    response_model=List[FindingCorrectionRead],
    status_code=status.HTTP_200_OK,
    summary="List corrections for a finding",
)
def get_corrections(
    id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> List[FindingCorrectionRead]:
    return correction_service.get_corrections_for_finding(
        db=db,
        finding_id=id,
    )


@router.get(
    "/evaluations/pending-review",
    response_model=PendingReviewQueueResponse,
    status_code=status.HTTP_200_OK,
    summary="Get confidence-aware prioritized teacher review queue",
)
def get_pending_review_queue(
    assessment_id: Optional[int] = Query(default=None, description="Optional assessment filter"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    sort: str = Query(default="priority", description="Sort order: 'priority' or 'created_at'"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> PendingReviewQueueResponse:
    return review_queue_service.get_pending_review_queue(
        db=db,
        assessment_id=assessment_id,
        page=page,
        page_size=page_size,
        sort=sort,
    )
