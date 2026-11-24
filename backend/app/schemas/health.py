from typing import Optional
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok"
            }
        }
    )


class AIHealthResponse(BaseModel):
    status: str  # "online" | "offline"
    provider: str
    model: Optional[str] = None
    error: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "online",
                "provider": "vllm",
                "model": "llama-3.3-70b-versatile",
                "error": None,
            }
        }
    )


class APIHealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    version: str
    environment: str
    api_version: str = "v1"
    ocr_provider: Optional[str] = None
    evaluator_provider: Optional[str] = None
    vllm_model: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "app_name": "LearnGraph",
                "version": "0.1.0",
                "environment": "development",
                "api_version": "v1",
            }
        }
    )
