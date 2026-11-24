from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.ocr import OCRExtraction


class OCRRepository:
    def get_by_id(self, db: Session, extraction_id: int) -> Optional[OCRExtraction]:
        return db.query(OCRExtraction).filter(OCRExtraction.id == extraction_id).first()

    def get_by_upload_id(self, db: Session, upload_id: int) -> Optional[OCRExtraction]:
        return (
            db.query(OCRExtraction)
            .filter(OCRExtraction.upload_id == upload_id)
            .order_by(OCRExtraction.id.desc())
            .first()
        )

    def create_or_update_extraction(
        self,
        db: Session,
        upload_id: int,
        extracted_text: Optional[str],
        structured_segments: Optional[List[Dict[str, Any]]],
        confidence: Optional[float],
        provider_name: str,
        processing_status: str,
        error_code: Optional[str] = None,
    ) -> OCRExtraction:
        record = self.get_by_upload_id(db, upload_id)
        if record:
            record.extracted_text = extracted_text
            record.structured_segments = structured_segments
            record.confidence = confidence
            record.provider_name = provider_name
            record.processing_status = processing_status
            record.error_code = error_code
        else:
            record = OCRExtraction(
                upload_id=upload_id,
                extracted_text=extracted_text,
                structured_segments=structured_segments,
                confidence=confidence,
                provider_name=provider_name,
                processing_status=processing_status,
                error_code=error_code,
            )
            db.add(record)

        db.commit()
        db.refresh(record)
        return record

    def delete_extraction(self, db: Session, db_obj: OCRExtraction) -> None:
        db.delete(db_obj)
        db.commit()


ocr_repository = OCRRepository()
