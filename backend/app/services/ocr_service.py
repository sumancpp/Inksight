from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.enums import UploadStatus
from app.models.submission import AnswerSheetUpload
from app.repositories.ocr_repository import ocr_repository
from app.repositories.upload_repository import upload_repository
from app.services.ocr.base import OCRAdapterError
from app.services.ocr.factory import get_ocr_adapter
from app.services.storage_service import storage_service


class OCRProcessingService:
    def trigger_processing(
        self,
        db: Session,
        upload_id: int,
        background_tasks: BackgroundTasks,
        force: bool = False,
    ) -> AnswerSheetUpload:
        """
        Validates upload record and current state, enqueues the extraction task,
        and marks the upload as QUEUED with concurrency guard.
        Allows force=True to re-queue stuck or interrupted tasks.
        """
        upload = upload_repository.get_by_id(db=db, upload_id=upload_id)
        if not upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Answer sheet upload with id {upload_id} not found.",
            )

        # Concurrency protection: reject duplicate triggers if currently queued or processing (unless force=True)
        if not force and upload.upload_status in [UploadStatus.QUEUED.value, UploadStatus.PROCESSING.value]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Upload {upload_id} is already being processed (status: {upload.upload_status}).",
            )

        # Transition upload state to QUEUED
        upload = upload_repository.update_status(db=db, db_obj=upload, new_status=UploadStatus.QUEUED)
        upload = upload_repository.update_progress(db=db, db_obj=upload, pages_completed=0, total_pages=0)

        # Enqueue background task (in-process background execution for local development)
        background_tasks.add_task(self.process_upload, upload_id=upload_id)

        return upload

    def get_session(self) -> Session:
        from app.main import app
        from app.core.database import get_db, SessionLocal
        if get_db in app.dependency_overrides:
            override = app.dependency_overrides[get_db]
            res = override()
            if hasattr(res, "__next__"):
                return next(res)
            return res
        return SessionLocal()

    async def process_upload(self, upload_id: int) -> None:
        """
        Background task execution unit. Manages its own database session.
        """
        from app.main import app
        from app.core.database import get_db
        is_override = get_db in app.dependency_overrides

        db = self.get_session()
        try:
            await self._execute_processing(db=db, upload_id=upload_id)
        finally:
            if not is_override:
                db.close()


    async def _execute_processing(self, db: Session, upload_id: int) -> None:
        upload = upload_repository.get_by_id(db=db, upload_id=upload_id)
        if not upload:
            logger.warning(f"Processing triggered for non-existent upload {upload_id}")
            return

        # 1. Confirm the file exists inside the configured upload directory
        try:
            file_path = storage_service.get_file_path(upload.stored_filename)
        except Exception:
            logger.error(f"Stored file for upload {upload_id} is inaccessible or missing")
            upload_repository.update_status(db=db, db_obj=upload, new_status=UploadStatus.FAILED)
            ocr_repository.create_or_update_extraction(
                db=db,
                upload_id=upload_id,
                extracted_text=None,
                structured_segments=None,
                confidence=0.0,
                provider_name=settings.OCR_PROVIDER,
                processing_status=UploadStatus.FAILED.value,
                error_code="FILE_INACCESSIBLE",
            )
            return

        # 2. Transition state to PROCESSING
        try:
            upload = upload_repository.update_status(
                db=db, db_obj=upload, new_status=UploadStatus.PROCESSING
            )
        except Exception as exc:
            logger.error(f"State transition error for upload {upload_id}: {exc}")
            return

        # 3. Call configured OCR adapter with progress tracking
        adapter = get_ocr_adapter()

        def on_ocr_progress(completed: int, total: int) -> None:
            try:
                upload_repository.update_progress(
                    db=db,
                    db_obj=upload,
                    pages_completed=completed,
                    total_pages=total,
                )
            except Exception as prog_err:
                logger.debug(f"Failed to persist OCR progress for upload {upload_id}: {prog_err}")

        try:
            result = await adapter.extract(file_path=file_path, on_progress=on_ocr_progress)
        except OCRAdapterError as exc:
            logger.error(f"OCR adapter execution failed for upload {upload_id} [code={exc.error_code}]")
            upload_repository.update_status(db=db, db_obj=upload, new_status=UploadStatus.FAILED)
            ocr_repository.create_or_update_extraction(
                db=db,
                upload_id=upload_id,
                extracted_text=None,
                structured_segments=None,
                confidence=0.0,
                provider_name=adapter.provider_name,
                processing_status=UploadStatus.FAILED.value,
                error_code=exc.error_code or "ADAPTER_EXECUTION_FAILED",
            )
            return
        except Exception as exc:
            logger.error(f"Unexpected error during OCR extraction for upload {upload_id}: {exc}")
            upload_repository.update_status(db=db, db_obj=upload, new_status=UploadStatus.FAILED)
            ocr_repository.create_or_update_extraction(
                db=db,
                upload_id=upload_id,
                extracted_text=None,
                structured_segments=None,
                confidence=0.0,
                provider_name=adapter.provider_name,
                processing_status=UploadStatus.FAILED.value,
                error_code="INTERNAL_PROCESSING_ERROR",
            )
            return

        # 4. Evaluate results for completeness and confidence
        is_empty = not result.extracted_text or not result.extracted_text.strip()
        is_low_confidence = (
            result.confidence is None
            or result.confidence < settings.OCR_LOW_CONFIDENCE_THRESHOLD
        )

        if is_empty:
            final_status = UploadStatus.NEEDS_REVIEW
            error_code = "EMPTY_EXTRACTION"
        elif is_low_confidence:
            final_status = UploadStatus.NEEDS_REVIEW
            error_code = "LOW_CONFIDENCE"
        else:
            final_status = UploadStatus.EXTRACTED
            error_code = None

        # 5. Persist extraction metadata and update upload status
        ocr_repository.create_or_update_extraction(
            db=db,
            upload_id=upload_id,
            extracted_text=result.extracted_text if not is_empty else None,
            structured_segments=result.structured_segments,
            confidence=result.confidence,
            provider_name=result.provider_name,
            processing_status=final_status.value,
            error_code=error_code,
        )
        upload_repository.update_status(db=db, db_obj=upload, new_status=final_status)
        logger.info(f"Processed upload {upload_id} -> {final_status.value}")


ocr_processing_service = OCRProcessingService()
