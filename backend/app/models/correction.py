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
from app.models.enums import CorrectionFieldName, CorrectionStatus


class FindingCorrection(Base):
    __tablename__ = "finding_corrections"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    finding_id = Column(
        Integer,
        ForeignKey("evaluation_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name = Column(String(50), nullable=False, index=True)
    original_value = Column(JSON, nullable=True)
    corrected_value = Column(JSON, nullable=False)
    corrected_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    corrected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    correction_reason = Column(Text, nullable=False)
    status = Column(
        String(50),
        nullable=False,
        default=CorrectionStatus.ACTIVE.value,
        index=True,
    )

    # Relationships
    finding = relationship("EvaluationFinding", back_populates="corrections")
    corrector = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<FindingCorrection(id={self.id}, finding_id={self.finding_id}, "
            f"field_name='{self.field_name}', status='{self.status}')>"
        )

