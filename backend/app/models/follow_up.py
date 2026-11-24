from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import FollowUpQuestionType, FollowUpStatus


class FollowUpQuestion(Base):
    __tablename__ = "follow_up_questions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    finding_id = Column(
        Integer,
        ForeignKey("evaluation_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept = Column(String(255), nullable=False)
    question_text = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=False)
    rubric = Column(JSON, nullable=False)
    question_type = Column(
        String(50),
        nullable=False,
        default=FollowUpQuestionType.SHORT_ANSWER.value,
    )
    status = Column(
        String(50),
        nullable=False,
        default=FollowUpStatus.PROPOSED.value,
        index=True,
    )
    proposed_by = Column(String(50), nullable=False, default="system")
    approved_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    audit_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    finding = relationship("EvaluationFinding", back_populates="follow_up_questions")
    assessment = relationship("Assessment")
    approver = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<FollowUpQuestion(id={self.id}, finding_id={self.finding_id}, "
            f"concept='{self.concept}', status='{self.status}')>"
        )

