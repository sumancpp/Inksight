from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import QuestionType


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    creator = relationship("User", back_populates="assessments")
    questions = relationship("Question", back_populates="assessment", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="assessment", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Assessment(id={self.id}, title='{self.title}', created_by={self.created_by})>"


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic_id = Column(
        Integer,
        ForeignKey("learning_topics.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt = Column(Text, nullable=False)
    question_type = Column(
        String(50),
        nullable=False,
        default=QuestionType.MULTIPLE_CHOICE.value,
    )
    marks = Column(Float, nullable=False, default=1.0)
    rubric = Column(Text, nullable=True)
    expected_answer = Column(Text, nullable=True)
    is_reference_proposed = Column(Boolean, default=False, nullable=False)
    reference_status = Column(String(50), default="approved", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    assessment = relationship("Assessment", back_populates="questions")
    topic = relationship("LearningTopic", back_populates="questions")
    answers = relationship("QuestionAnswer", back_populates="question", cascade="all, delete-orphan")
    proposed_answers = relationship("ProposedAnswer", back_populates="question", cascade="all, delete-orphan")
    evaluation_runs = relationship("EvaluationRun", back_populates="question", cascade="all, delete-orphan")


    def __repr__(self) -> str:

        return f"<Question(id={self.id}, assessment_id={self.assessment_id}, type='{self.question_type}')>"
