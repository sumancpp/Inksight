from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import UploadStatus
from app.models.submission import AnswerSheetUpload


class UploadRepository:
    def get_by_id(self, db: Session, upload_id: int) -> Optional[AnswerSheetUpload]:
        return db.query(AnswerSheetUpload).filter(AnswerSheetUpload.id == upload_id).first()

    def get_multi_by_submission(
        self, db: Session, submission_id: int, limit: int = 20, offset: int = 0
    ) -> Tuple[List[AnswerSheetUpload], int]:
        total = (
            db.query(func.count(AnswerSheetUpload.id))
            .filter(AnswerSheetUpload.submission_id == submission_id)
            .scalar()
            or 0
        )
        items = (
            db.query(AnswerSheetUpload)
            .filter(AnswerSheetUpload.submission_id == submission_id)
            .order_by(AnswerSheetUpload.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def create_upload(
        self,
        db: Session,
        submission_id: int,
        original_filename: str,
        stored_filename: str,
        storage_path: str,
        content_type: str,
        file_size_bytes: int,
        upload_status: UploadStatus = UploadStatus.UPLOADED,
    ) -> AnswerSheetUpload:
        status_val = (
            upload_status.value
            if hasattr(upload_status, "value")
            else str(upload_status)
        )
        db_obj = AnswerSheetUpload(
            submission_id=submission_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            storage_path=storage_path,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            upload_status=status_val,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_status(
        self, db: Session, db_obj: AnswerSheetUpload, new_status: UploadStatus | str
    ) -> AnswerSheetUpload:
        from app.models.enums import validate_upload_transition
        status_enum = UploadStatus(new_status) if isinstance(new_status, str) else new_status
        current_enum = UploadStatus(db_obj.upload_status)
        validate_upload_transition(current=current_enum, target=status_enum)
        db_obj.upload_status = status_enum.value
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_progress(
        self, db: Session, db_obj: AnswerSheetUpload, pages_completed: int, total_pages: int
    ) -> AnswerSheetUpload:
        db_obj.pages_completed = pages_completed
        db_obj.total_pages = total_pages
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete_upload(self, db: Session, db_obj: AnswerSheetUpload) -> None:
        db.delete(db_obj)
        db.commit()


upload_repository = UploadRepository()

