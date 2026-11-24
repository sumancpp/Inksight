from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UploadStatus


class AnswerSheetUploadBase(BaseModel):
    original_filename: str = Field(..., description="Original name of the uploaded file")
    content_type: str = Field(..., description="MIME content type")
    file_size_bytes: int = Field(..., ge=0, description="Size of the file in bytes")
    upload_status: UploadStatus = Field(
        default=UploadStatus.UPLOADED,
        description="Status of the upload: uploaded, pending_review, or rejected",
    )


class AnswerSheetUploadRead(AnswerSheetUploadBase):
    id: int
    submission_id: int
    stored_filename: str = Field(..., description="Unique server-generated filename")
    uploaded_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
