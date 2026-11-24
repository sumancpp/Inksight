from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import require_active_user
from app.core.database import get_db
from app.core.logging import logger
from app.models.enums import UploadStatus, UserRole
from app.models.user import User
from app.repositories.ocr_repository import ocr_repository
from app.repositories.submission_repository import submission_repository
from app.repositories.upload_repository import upload_repository
from app.schemas.common import PaginatedResponse
from app.schemas.ocr import (
    OCRExtractionRead,
    OCRProcessTriggerResponse,
    ProcessingStatusRead,
)
from app.services.ocr.layout import detect_math_content
from app.schemas.upload import AnswerSheetUploadRead
from app.services.ocr_service import ocr_processing_service
from app.services.storage_service import storage_service

router = APIRouter()


def _assert_submission_upload_access(submission, user: User, action_desc: str = "access") -> None:
    user_role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    if user_role == UserRole.STUDENT.value and submission.student_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not authorized to {action_desc} this answer sheet",
        )


@router.post(
    "/submissions/{submission_id}/answer-sheets",
    response_model=AnswerSheetUploadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an answer sheet file for a submission",
)
async def upload_answer_sheet(
    submission_id: int,
    file: UploadFile = File(..., description="Scanned answer sheet (PDF, JPEG, or PNG)"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> AnswerSheetUploadRead:
    # 1. Validate submission exists before accepting or saving file
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )

    _assert_submission_upload_access(submission, current_user, "upload to")

    # 2. Strict file validation (extension, size, python-magic bytes, malware scan)
    await storage_service.validate_upload(file)

    # 3. Save file stream safely
    original_filename, stored_filename, storage_path, content_type, file_size_bytes = (
        await storage_service.save_upload(file)
    )

    # 3. Persist metadata in database, cleaning up file if persistence fails
    try:
        upload_record = upload_repository.create_upload(
            db=db,
            submission_id=submission_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            storage_path=storage_path,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            upload_status=UploadStatus.UPLOADED,
        )
    except Exception as exc:
        logger.error(
            f"Database persistence failed for upload '{stored_filename}', cleaning up stored file: {exc}"
        )
        storage_service.delete_file(stored_filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record upload metadata.",
        )

    return upload_record


@router.get(
    "/submissions/{submission_id}/answer-sheets",
    response_model=PaginatedResponse[AnswerSheetUploadRead],
    summary="List uploaded answer sheet metadata for a submission",
)
def list_submission_answer_sheets(
    submission_id: int,
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AnswerSheetUploadRead]:
    submission = submission_repository.get_by_id(db=db, submission_id=submission_id)
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission with id {submission_id} not found.",
        )

    _assert_submission_upload_access(submission, current_user, "view answer sheets for")

    items, total = upload_repository.get_multi_by_submission(
        db=db, submission_id=submission_id, limit=limit, offset=offset
    )
    return PaginatedResponse(
        items=[AnswerSheetUploadRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/answer-sheets/{upload_id}",
    response_model=AnswerSheetUploadRead,
    summary="Retrieve metadata for a specific answer sheet upload",
)
def get_answer_sheet_metadata(
    upload_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> AnswerSheetUploadRead:
    upload_record = upload_repository.get_by_id(db=db, upload_id=upload_id)
    if not upload_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer sheet upload with id {upload_id} not found.",
        )

    submission = submission_repository.get_by_id(db=db, submission_id=upload_record.submission_id)
    if submission:
        _assert_submission_upload_access(submission, current_user, "view")

    return upload_record


@router.get(
    "/answer-sheets/{upload_id}/file",
    summary="Download the stored answer sheet file",
)
def download_answer_sheet_file(
    upload_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    upload_record = upload_repository.get_by_id(db=db, upload_id=upload_id)
    if not upload_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer sheet upload with id {upload_id} not found.",
        )

    submission = submission_repository.get_by_id(db=db, submission_id=upload_record.submission_id)
    if submission:
        _assert_submission_upload_access(submission, current_user, "download")

    # Securely retrieve verified file path inside storage directory
    file_path = storage_service.get_file_path(upload_record.stored_filename)

    return FileResponse(
        path=str(file_path),
        media_type=upload_record.content_type,
        filename=upload_record.original_filename,
    )


@router.post(
    "/answer-sheets/{upload_id}/process",
    response_model=OCRProcessTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger OCR extraction for an answer sheet in the background",
)
def process_answer_sheet(
    upload_id: int,
    background_tasks: BackgroundTasks,
    force: bool = False,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> OCRProcessTriggerResponse:
    upload_record = upload_repository.get_by_id(db=db, upload_id=upload_id)
    if not upload_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer sheet upload with id {upload_id} not found.",
        )

    submission = submission_repository.get_by_id(db=db, submission_id=upload_record.submission_id)
    if submission:
        _assert_submission_upload_access(submission, current_user, "process")

    upload = ocr_processing_service.trigger_processing(
        db=db, upload_id=upload_id, background_tasks=background_tasks, force=force
    )
    return OCRProcessTriggerResponse(
        upload_id=upload.id,
        status=UploadStatus(upload.upload_status),
        message="Answer sheet queued for OCR extraction.",
    )


@router.get(
    "/answer-sheets/{upload_id}/status",
    response_model=ProcessingStatusRead,
    include_in_schema=False,
)
@router.get(
    "/answer-sheets/{upload_id}/processing-status",
    response_model=ProcessingStatusRead,
    summary="Get processing status for an uploaded answer sheet",
)
def get_processing_status(
    upload_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> ProcessingStatusRead:
    upload = upload_repository.get_by_id(db=db, upload_id=upload_id)
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer sheet upload with id {upload_id} not found.",
        )

    submission = submission_repository.get_by_id(db=db, submission_id=upload.submission_id)
    if submission:
        _assert_submission_upload_access(submission, current_user, "view processing status for")

    extraction = ocr_repository.get_by_upload_id(db=db, upload_id=upload_id)
    total_pages = getattr(upload, "total_pages", None) or 0
    pages_completed = getattr(upload, "pages_completed", None) or 0
    progress_pct = None
    if total_pages > 0:
        progress_pct = round((pages_completed / total_pages) * 100.0, 1)

    return ProcessingStatusRead(
        upload_id=upload.id,
        upload_status=UploadStatus(upload.upload_status),
        has_extraction=extraction is not None,
        latest_error_code=extraction.error_code if extraction else None,
        updated_at=extraction.updated_at if extraction else upload.uploaded_at,
        total_pages=total_pages if total_pages > 0 else None,
        pages_completed=pages_completed,
        progress_percent=progress_pct,
    )


@router.get(
    "/answer-sheets/{upload_id}/extraction",
    response_model=OCRExtractionRead,
    summary="Retrieve OCR extraction result for an answer sheet",
)
def get_answer_sheet_extraction(
    upload_id: int,
    current_user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> OCRExtractionRead:
    upload = upload_repository.get_by_id(db=db, upload_id=upload_id)
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer sheet upload with id {upload_id} not found.",
        )

    submission = submission_repository.get_by_id(db=db, submission_id=upload.submission_id)
    if submission:
        _assert_submission_upload_access(submission, current_user, "view extraction for")

    extraction = ocr_repository.get_by_upload_id(db=db, upload_id=upload_id)
    if not extraction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OCR extraction for upload id {upload_id} not found or not yet processed (current status: {upload.upload_status}).",
        )

    has_math, math_warnings = detect_math_content(extraction.extracted_text)
    return OCRExtractionRead(
        id=extraction.id,
        upload_id=extraction.upload_id,
        extracted_text=extraction.extracted_text,
        structured_segments=extraction.structured_segments,
        confidence=extraction.confidence,
        provider_name=extraction.provider_name,
        processing_status=extraction.processing_status,
        error_code=extraction.error_code,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
        has_math_content=has_math,
        quality_warnings=math_warnings if has_math else None,
    )
