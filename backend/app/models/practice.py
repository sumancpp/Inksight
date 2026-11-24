from sqlalchemy import (
    Boolean,
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
from app.models.enums import PracticeSessionStatus


class PracticeSession(Base):
    __tablename__ = "practice_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id = Column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        String(50),
        nullable=False,
        default=PracticeSessionStatus.ACTIVE.value,
        index=True,
    )
    total_items = Column(Integer, nullable=False, default=0)
    completed_items = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    student = relationship("User")
    submission = relationship("Submission")
    responses = relationship(
        "PracticeResponse",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PracticeResponse.id",
    )

    def __repr__(self) -> str:
        return (
            f"<PracticeSession(id={self.id}, student_id={self.student_id}, "
            f"submission_id={self.submission_id}, status='{self.status}')>"
        )


class PracticeResponse(Base):
    __tablename__ = "practice_responses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    remediation_item_id = Column(
        Integer,
        ForeignKey("remediation_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id = Column(
        Integer,
        ForeignKey("evaluation_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_run_id = Column(
        Integer,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_answer = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    score = Column(Float, nullable=False, default=0.0)
    feedback = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "remediation_item_id",
            name="uq_practice_session_item_response",
        ),
    )

    # Relationships
    session = relationship("PracticeSession", back_populates="responses")
    remediation_item = relationship("RemediationItem")
    finding = relationship("EvaluationFinding")
    evaluation_run = relationship("EvaluationRun")

    def __repr__(self) -> str:
        return (
            f"<PracticeResponse(id={self.id}, session_id={self.session_id}, "
            f"item_id={self.remediation_item_id}, is_correct={self.is_correct})>"
        )
