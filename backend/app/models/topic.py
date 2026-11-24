from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class LearningTopic(Base):
    __tablename__ = "learning_topics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    questions = relationship("Question", back_populates="topic")

    def __repr__(self) -> str:
        return f"<LearningTopic(id={self.id}, name='{self.name}')>"
