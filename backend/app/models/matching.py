from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ProposalStatus


class ProposedAnswer(Base):
    __tablename__ = "proposed_answers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    upload_id = Column(
        Integer,
        ForeignKey("answer_sheet_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ocr_extraction_id = Column(
        Integer,
        ForeignKey("ocr_extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    segment_id = Column(Integer, nullable=True)
    proposed_text = Column(Text, nullable=False)
    corrected_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    status = Column(
        String(50),
        nullable=False,
        default=ProposalStatus.PROPOSED.value,
        index=True,
    )
    rejection_reason = Column(String(255), nullable=True)
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("upload_id", "segment_id", name="uq_proposal_upload_segment"),
    )

    # Relationships
    submission = relationship("Submission", back_populates="proposed_answers")
    upload = relationship("AnswerSheetUpload", back_populates="proposed_answers")
    ocr_extraction = relationship("OCRExtraction", back_populates="proposed_answers")
    question = relationship("Question", back_populates="proposed_answers")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    reviews = relationship("TeacherReview", back_populates="proposal", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<ProposedAnswer(id={self.id}, submission_id={self.submission_id}, "
            f"question_id={self.question_id}, status='{self.status}')>"
        )


class TeacherReview(Base):
    __tablename__ = "teacher_reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    proposal_id = Column(
        Integer,
        ForeignKey("proposed_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action = Column(String(50), nullable=False)
    original_text = Column(Text, nullable=False)
    final_text = Column(Text, nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    proposal = relationship("ProposedAnswer", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewer_id])

    def __repr__(self) -> str:
        return (
            f"<TeacherReview(id={self.id}, proposal_id={self.proposal_id}, "
            f"reviewer_id={self.reviewer_id}, action='{self.action}')>"
        )
