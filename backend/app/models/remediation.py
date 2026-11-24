from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import PracticeItemReviewStatus, PracticeQuestionType, RemediationRunStatus


class RemediationRun(Base):
    __tablename__ = "remediation_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
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
    generator_name = Column(String(100), nullable=False)
    status = Column(
        String(50),
        nullable=False,
        default=RemediationRunStatus.PENDING.value,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "finding_id",
            "generator_name",
            name="uq_remediation_finding_generator",
        ),
    )

    # Relationships
    finding = relationship("EvaluationFinding", back_populates="remediation_runs")
    evaluation_run = relationship("EvaluationRun", back_populates="remediation_runs")
    items = relationship("RemediationItem", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<RemediationRun(id={self.id}, finding_id={self.finding_id}, "
            f"generator='{self.generator_name}', status='{self.status}')>"
        )


class RemediationItem(Base):
    __tablename__ = "remediation_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("remediation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id = Column(
        Integer,
        ForeignKey("evaluation_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_concept = Column(String(255), nullable=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(
        String(50),
        nullable=False,
        default=PracticeQuestionType.SHORT_ANSWER.value,
    )
    options = Column(JSON, nullable=True)
    teacher_answer_key = Column(Text, nullable=True)
    teacher_rationale = Column(Text, nullable=True)
    difficulty = Column(String(50), nullable=True)
    uncertainty_note = Column(Text, nullable=True)
    review_status = Column(
        String(50),
        nullable=False,
        default=PracticeItemReviewStatus.PENDING_REVIEW.value,
        index=True,
    )
    edited_question_text = Column(Text, nullable=True)
    edited_answer_key = Column(Text, nullable=True)
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    run = relationship("RemediationRun", back_populates="items")
    finding = relationship("EvaluationFinding", back_populates="remediation_items")
    reviewer = relationship("User")
    audits = relationship(
        "RemediationItemAudit",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<RemediationItem(id={self.id}, run_id={self.run_id}, "
            f"type='{self.question_type}', review_status='{self.review_status}')>"
        )


class RemediationItemAudit(Base):
    __tablename__ = "remediation_item_audits"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    item_id = Column(
        Integer,
        ForeignKey("remediation_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(50), nullable=False)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    edited_question_text = Column(Text, nullable=True)
    edited_answer_key = Column(Text, nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    item = relationship("RemediationItem", back_populates="audits")
    reviewer = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<RemediationItemAudit(id={self.id}, item_id={self.item_id}, "
            f"reviewer_id={self.reviewer_id}, action='{self.action}')>"
        )
