from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class OCRExtraction(Base):
    __tablename__ = "ocr_extractions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    upload_id = Column(
        Integer,
        ForeignKey("answer_sheet_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extracted_text = Column(Text, nullable=True)
    structured_segments = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    provider_name = Column(String(100), nullable=False)
    processing_status = Column(String(50), nullable=False)
    error_code = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    upload = relationship("AnswerSheetUpload", back_populates="extractions")
    proposed_answers = relationship("ProposedAnswer", back_populates="ocr_extraction", cascade="all, delete-orphan")

    def __repr__(self) -> str:

        return (
            f"<OCRExtraction(id={self.id}, upload_id={self.upload_id}, "
            f"provider='{self.provider_name}', status='{self.processing_status}')>"
        )
