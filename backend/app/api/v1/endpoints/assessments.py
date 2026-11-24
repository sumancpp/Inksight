from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_active_user, require_student, require_teacher
from app.core.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.assessment_repository import assessment_repository
from app.repositories.question_repository import question_repository
from app.repositories.submission_repository import submission_repository
from app.repositories.topic_repository import topic_repository
from app.schemas.assessment import AssessmentCreate, AssessmentRead, AssessmentUpdate
from app.schemas.common import PaginatedResponse
from app.schemas.question import ApproveReferenceRequest, QuestionCreate, QuestionRead
from app.schemas.submission import SubmissionCreate, SubmissionRead
from app.services.question_ingestion_service import question_ingestion_service
from app.services.storage_service import storage_service

router = APIRouter()


@router.post(
    "",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new assessment",
)
def create_assessment(
    assessment_in: AssessmentCreate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AssessmentRead:
    """Create assessment with created_by derived strictly from authenticated teacher."""
    return assessment_repository.create(
        db=db, obj_in=assessment_in, created_by=current_user.id
    )


@router.get(
    "",
    response_model=PaginatedResponse[AssessmentRead],
    summary="List assessments with pagination",
)
def list_assessments(
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AssessmentRead]:
    items, total = assessment_repository.get_multi(db=db, limit=limit, offset=offset)
    return PaginatedResponse[AssessmentRead](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{assessment_id}",
    response_model=AssessmentRead,
    summary="Get an assessment by ID",
)
def get_assessment(
    assessment_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> AssessmentRead:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )
    return assessment


@router.patch(
    "/{assessment_id}",
    response_model=AssessmentRead,
    summary="Update an assessment",
)
def update_assessment(
    assessment_id: int,
    assessment_in: AssessmentUpdate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> AssessmentRead:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this assessment",
        )

    return assessment_repository.update(db=db, db_obj=assessment, obj_in=assessment_in)


@router.delete(
    "/{assessment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an assessment and its associated questions",
)
def delete_assessment(
    assessment_id: int,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this assessment",
        )

    assessment_repository.delete(db=db, db_obj=assessment)


# Nested Question endpoints under /assessments/{assessment_id}/questions
@router.post(
    "/{assessment_id}/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a question within an assessment",
    tags=["Questions"],
)
def create_question_for_assessment(
    assessment_id: int,
    question_in: QuestionCreate,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> QuestionRead:
    # 1. Verify assessment exists
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to add questions to this assessment",
        )

    # 2. Verify learning topic exists
    topic = topic_repository.get_by_id(db=db, topic_id=question_in.topic_id)
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Learning topic with id {question_in.topic_id} not found.",
        )

    return question_repository.create(db=db, assessment_id=assessment_id, obj_in=question_in)


@router.get(
    "/{assessment_id}/questions",
    response_model=PaginatedResponse[QuestionRead],
    summary="List all questions for an assessment with pagination",
    tags=["Questions"],
)
def list_questions_for_assessment(
    assessment_id: int,
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[QuestionRead]:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    items, total = question_repository.get_multi_by_assessment(
        db=db, assessment_id=assessment_id, limit=limit, offset=offset
    )
    return PaginatedResponse[QuestionRead](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# Nested Submission endpoints under /assessments/{assessment_id}/submissions
@router.post(
    "/{assessment_id}/submissions",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new submission for an assessment",
    tags=["Submissions"],
)
def create_submission_for_assessment(
    assessment_id: int,
    submission_in: SubmissionCreate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
) -> SubmissionRead:
    """Create submission deriving student identity strictly from authenticated student."""
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    return submission_repository.create_submission(
        db=db,
        assessment_id=assessment_id,
        obj_in=submission_in,
        student_id=current_user.id,
    )


@router.get(
    "/{assessment_id}/submissions",
    response_model=PaginatedResponse[SubmissionRead],
    summary="List all submissions for an assessment with pagination",
    tags=["Submissions"],
)
def list_submissions_for_assessment(
    assessment_id: int,
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SubmissionRead]:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    # Students only see their own submissions; teachers and admins see all
    student_filter = (
        current_user.id
        if (current_user.role == UserRole.STUDENT.value or current_user.role == UserRole.STUDENT)
        else None
    )

    items, total = submission_repository.get_multi_by_assessment(
        db=db,
        assessment_id=assessment_id,
        limit=limit,
        offset=offset,
        student_id=student_filter,
    )
    return PaginatedResponse[SubmissionRead](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{assessment_id}/upload-question-paper",
    response_model=List[QuestionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a question paper file and extract questions with proposed reference keys",
    tags=["Questions"],
)
async def upload_question_paper(
    assessment_id: int,
    file: UploadFile = File(..., description="Question paper document (PDF, PNG, JPEG)"),
    topic_id: Optional[int] = Query(None, description="Optional default topic ID for extracted questions"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> List[QuestionRead]:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    if current_user.role != UserRole.ADMIN.value and assessment.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload question paper for this assessment",
        )

    # Validate uploaded question paper (extension, size, magic numbers, malware)
    await storage_service.validate_upload(file)

    # Save uploaded question paper
    _, stored_filename, _, _, _ = await storage_service.save_upload(file)

    # Extract questions and propose reference solutions
    return await question_ingestion_service.extract_and_create_questions_from_paper(
        db=db,
        assessment_id=assessment_id,
        stored_filename=stored_filename,
        default_topic_id=topic_id,
    )


@router.post(
    "/{assessment_id}/generate-reference-keys",
    response_model=List[QuestionRead],
    summary="Generate proposed reference keys and rubrics for assessment questions lacking them",
    tags=["Questions"],
)
def generate_reference_keys(
    assessment_id: int,
    force: bool = Query(default=True, description="Whether to generate reference keys for all questions in assessment"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> List[QuestionRead]:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    return question_ingestion_service.generate_reference_keys_for_assessment(
        db=db, assessment_id=assessment_id, force=force
    )


@router.post(
    "/{assessment_id}/questions/{question_id}/approve-reference",
    response_model=QuestionRead,
    summary="Approve or update a proposed reference solution and rubric for a question",
    tags=["Questions"],
)
def approve_question_reference(
    assessment_id: int,
    question_id: int,
    request: ApproveReferenceRequest,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> QuestionRead:
    assessment = assessment_repository.get_by_id(db=db, assessment_id=assessment_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found.",
        )

    return question_ingestion_service.approve_question_reference(
        db=db, assessment_id=assessment_id, question_id=question_id, request=request
    )
