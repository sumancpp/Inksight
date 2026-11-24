from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class LearningTopicBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Topic name")
    description: Optional[str] = Field(None, description="Detailed topic description")


class LearningTopicCreate(LearningTopicBase):
    pass


class LearningTopicUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class LearningTopicRead(LearningTopicBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
