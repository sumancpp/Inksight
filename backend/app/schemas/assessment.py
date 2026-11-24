from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AssessmentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Assessment title")
    description: Optional[str] = Field(None, description="Optional assessment description")


class AssessmentCreate(AssessmentBase):
    pass


class AssessmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class AssessmentRead(AssessmentBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
