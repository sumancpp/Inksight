from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_student
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.question_repository import question_repository
from app.repositories.submission_repository import submission_repository
from app.schemas.common import PaginatedResponse
from app.schemas.submission import (
    QuestionAnswerCreate,
    QuestionAnswerRead,
    QuestionAnswerUpdate,
    SubmissionRead,
    SubmissionUpdate,
)

router = APIRouter()


def _assert_submission_access(submission, user: User) -> None:
    """Verifies that if user is a student, they own the submission."""
    user_role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    if user_role == UserRole.STUDENT.value and submission.student_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this submission",
        )


@router.get(
    "/{submission_id}",
    response_model=SubmissionRead,
    summary="Get a submission by ID",
)
def get_submission(
    submission_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> SubmissionRead:
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )
    _assert_submission_access(submission, current_user)
    return submission


@router.patch(
    "/{submission_id}",
    response_model=SubmissionRead,
    summary="Update submission status or submitted timestamp",
)
def update_submission(
    submission_id: int,
    submission_in: SubmissionUpdate,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> SubmissionRead:
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )
    _assert_submission_access(submission, current_user)
    return submission_repository.update_submission(db=db, db_obj=submission, obj_in=submission_in)


@router.post(
    "/{submission_id}/answers",
    response_model=QuestionAnswerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an answer to a question within a submission",
)
def create_answer(
    submission_id: int,
    answer_in: QuestionAnswerCreate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> QuestionAnswerRead:
    # 1. Verify submission exists
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )

    _assert_submission_access(submission, current_user)

    # 2. Verify question exists
    question = question_repository.get_by_id(db=db, question_id=answer_in.question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with id {answer_in.question_id} not found.",
        )

    # 3. Verify question belongs to the assessment associated with this submission
    if question.assessment_id != submission.assessment_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Question {question.id} belongs to assessment {question.assessment_id}, "
                f"not to submission assessment {submission.assessment_id}."
            ),
        )

    # 4. Prevent duplicate answers for the same question within the submission
    existing = submission_repository.get_answer_by_submission_and_question(
        db=db, submission_id=submission_id, question_id=answer_in.question_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An answer for question {answer_in.question_id} already exists in submission {submission_id}.",
        )

    # 5. Validate awarded marks within bounds [0, question.marks]
    if answer_in.awarded_marks is not None:
        if answer_in.awarded_marks < 0 or answer_in.awarded_marks > question.marks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"awarded_marks must be between 0.0 and {question.marks} (question max marks).",
            )

    return submission_repository.create_answer(db=db, submission_id=submission_id, obj_in=answer_in)


@router.patch(
    "/{submission_id}/answers/{answer_id}",
    response_model=QuestionAnswerRead,
    summary="Update a question answer (e.g. answer text or awarded marks)",
)
def update_answer(
    submission_id: int,
    answer_id: int,
    answer_in: QuestionAnswerUpdate,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> QuestionAnswerRead:
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )

    _assert_submission_access(submission, current_user)

    answer = submission_repository.get_answer_by_id(db=db, answer_id=answer_id)
    if not answer or answer.submission_id != submission_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer with id {answer_id} not found in submission {submission_id}.",
        )

    # Validate awarded marks against question maximum
    if answer_in.awarded_marks is not None:
        max_marks = answer.question.marks
        if answer_in.awarded_marks < 0 or answer_in.awarded_marks > max_marks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"awarded_marks must be between 0.0 and {max_marks} (question max marks).",
            )

    return submission_repository.update_answer(db=db, db_obj=answer, obj_in=answer_in)


@router.get(
    "/{submission_id}/answers",
    response_model=PaginatedResponse[QuestionAnswerRead],
    summary="List all answers for a submission with pagination",
)
def list_answers(
    submission_id: int,
    limit: int = Query(default=50, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[QuestionAnswerRead]:
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )

    _assert_submission_access(submission, current_user)

    items, total = submission_repository.get_answers_for_submission(
        db=db, submission_id=submission_id, limit=limit, offset=offset
    )
    return PaginatedResponse[QuestionAnswerRead](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
