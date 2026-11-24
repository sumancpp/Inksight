from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UploadStatus


class OCRExtractionSegment(BaseModel):
    segment_id: int
    page: Optional[int] = 1
    text: str
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    bounding_box: Optional[List[float]] = None


class OCRExtractionRead(BaseModel):
    id: int
    upload_id: int
    extracted_text: Optional[str] = None
    structured_segments: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    provider_name: str
    processing_status: str
    error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    has_math_content: Optional[bool] = False
    quality_warnings: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class OCRProcessTriggerResponse(BaseModel):
    upload_id: int
    status: UploadStatus
    message: str


class ProcessingStatusRead(BaseModel):
    upload_id: int
    upload_status: UploadStatus
    has_extraction: bool
    latest_error_code: Optional[str] = None
    updated_at: Optional[datetime] = None
    total_pages: Optional[int] = None
    pages_completed: Optional[int] = None
    progress_percent: Optional[float] = None
