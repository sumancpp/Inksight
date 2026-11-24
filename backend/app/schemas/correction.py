from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CorrectionFieldName, CorrectionStatus


class FindingCorrectionCreate(BaseModel):
    field_name: CorrectionFieldName
    corrected_value: Any
    correction_reason: str = Field(..., min_length=1)


class FindingCorrectionRead(BaseModel):
    id: int
    finding_id: int
    field_name: CorrectionFieldName
    original_value: Optional[Any] = None
    corrected_value: Any
    corrected_by: Optional[int] = None
    corrected_at: datetime
    correction_reason: str
    status: CorrectionStatus

    model_config = ConfigDict(from_attributes=True)

