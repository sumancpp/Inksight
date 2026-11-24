from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
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
from app.models.enums import EvaluationStatus, FindingReviewStatus


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

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
    question_answer_id = Column(
        Integer,
        ForeignKey("question_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluator_name = Column(String(100), nullable=False)
    status = Column(
        String(50),
        nullable=False,
        default=EvaluationStatus.PENDING.value,
        index=True,
    )
    answer_text_hash = Column(String(64), nullable=False, index=True)
    answer_text_snapshot = Column(Text, nullable=False)
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
            "submission_id",
            "question_id",
            "answer_text_hash",
            name="uq_run_submission_question_hash",
        ),
    )

    # Relationships
    submission = relationship("Submission", back_populates="evaluation_runs")
    question = relationship("Question", back_populates="evaluation_runs")
    question_answer = relationship("QuestionAnswer", back_populates="evaluation_runs")
    findings = relationship("EvaluationFinding", back_populates="run", cascade="all, delete-orphan")
    remediation_runs = relationship("RemediationRun", back_populates="evaluation_run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<EvaluationRun(id={self.id}, submission_id={self.submission_id}, "
            f"question_id={self.question_id}, status='{self.status}')>"
        )


class EvaluationFinding(Base):
    __tablename__ = "evaluation_findings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(
        Integer,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(
        Integer,
        ForeignKey("learning_topics.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    concept_name = Column(String(255), nullable=True)
    category = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    uncertainty_rationale = Column(Text, nullable=True)
    evidence_excerpt = Column(Text, nullable=True)
    rationale = Column(Text, nullable=False)
    verdict = Column(String(50), nullable=True, index=True)
    correct_answer = Column(Text, nullable=True)
    marks_awarded = Column(Float, nullable=True)
    max_marks = Column(Float, nullable=True)
    marks_reason = Column(Text, nullable=True)
    error_amount = Column(String(100), nullable=True)
    error_type = Column(String(100), nullable=True)
    step_by_step_explanation = Column(Text, nullable=True)
    _misconception_hypothesis = Column("misconception_hypothesis", Text, nullable=True)
    remediation_concept = Column(String(255), nullable=True)
    follow_up_question = Column(Text, nullable=True)
    misconceptions = Column(JSON, nullable=False, default=list)
    confidence_details = Column(JSON, nullable=True)
    requires_teacher_review = Column(Boolean, nullable=False, default=False)
    acknowledged_uncertainty = Column(Boolean, nullable=False, default=False)

    @property
    def misconception_hypothesis(self) -> str | None:
        if self.misconceptions and len(self.misconceptions) > 0:
            first = self.misconceptions[0]
            if isinstance(first, dict):
                return first.get("hypothesis")
            return getattr(first, "hypothesis", None)
        return self._misconception_hypothesis

    @misconception_hypothesis.setter
    def misconception_hypothesis(self, value: str | None) -> None:
        self._misconception_hypothesis = value
    review_status = Column(
        String(50),
        nullable=False,
        default=FindingReviewStatus.PENDING_REVIEW.value,
        index=True,
    )
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
    run = relationship("EvaluationRun", back_populates="findings")
    topic = relationship("LearningTopic")
    reviewer = relationship("User")
    review_history = relationship(
        "FindingReviewAudit",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    remediation_runs = relationship(
        "RemediationRun",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    remediation_items = relationship(
        "RemediationItem",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    follow_up_questions = relationship(
        "FollowUpQuestion",
        back_populates="finding",
        cascade="all, delete-orphan",
    )
    corrections = relationship(
        "FindingCorrection",
        back_populates="finding",
        cascade="all, delete-orphan",
    )

    @property
    def teacher_corrected(self) -> bool:
        if not self.corrections:
            return False
        return any(getattr(c, "status", None) == "active" for c in self.corrections)

    def __repr__(self) -> str:
        return (
            f"<EvaluationFinding(id={self.id}, run_id={self.run_id}, "
            f"category='{self.category}', confidence={self.confidence})>"
        )


class FindingReviewAudit(Base):
    __tablename__ = "finding_review_audits"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    finding_id = Column(
        Integer,
        ForeignKey("evaluation_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewer_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(50), nullable=False)
    review_notes = Column(Text, nullable=True)
    acknowledged_uncertainty = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    finding = relationship("EvaluationFinding", back_populates="review_history")
    reviewer = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<FindingReviewAudit(id={self.id}, finding_id={self.finding_id}, "
            f"reviewer_id={self.reviewer_id}, action='{self.action}')>"
        )
