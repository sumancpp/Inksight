from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import SubmissionStatus, UploadStatus


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(50),
        nullable=False,
        default=SubmissionStatus.DRAFT.value,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    assessment = relationship("Assessment", back_populates="submissions")
    student = relationship("User", back_populates="submissions")
    answers = relationship("QuestionAnswer", back_populates="submission", cascade="all, delete-orphan")
    answer_sheets = relationship("AnswerSheetUpload", back_populates="submission", cascade="all, delete-orphan")
    proposed_answers = relationship("ProposedAnswer", back_populates="submission", cascade="all, delete-orphan")
    evaluation_runs = relationship("EvaluationRun", back_populates="submission", cascade="all, delete-orphan")

    def __repr__(self) -> str:

        return f"<Submission(id={self.id}, assessment_id={self.assessment_id}, student_id={self.student_id}, status='{self.status}')>"


class QuestionAnswer(Base):
    __tablename__ = "question_answers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_text = Column(Text, nullable=True)
    awarded_marks = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("submission_id", "question_id", name="uq_submission_question"),
    )

    # Relationships
    submission = relationship("Submission", back_populates="answers")
    question = relationship("Question", back_populates="answers")
    evaluation_runs = relationship("EvaluationRun", back_populates="question_answer", cascade="all, delete-orphan")


    def __repr__(self) -> str:
        return f"<QuestionAnswer(id={self.id}, submission_id={self.submission_id}, question_id={self.question_id}, awarded_marks={self.awarded_marks})>"


class AnswerSheetUpload(Base):
    __tablename__ = "answer_sheet_uploads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), unique=True, index=True, nullable=False)
    storage_path = Column(String(1024), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    upload_status = Column(
        String(50),
        nullable=False,
        default=UploadStatus.UPLOADED.value,
    )
    total_pages = Column(Integer, nullable=True, default=0)
    pages_completed = Column(Integer, nullable=True, default=0)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="answer_sheets")
    extractions = relationship("OCRExtraction", back_populates="upload", cascade="all, delete-orphan")
    proposed_answers = relationship("ProposedAnswer", back_populates="upload", cascade="all, delete-orphan")

    def __repr__(self) -> str:

        return f"<AnswerSheetUpload(id={self.id}, submission_id={self.submission_id}, filename='{self.stored_filename}')>"

