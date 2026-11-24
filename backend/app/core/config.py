from pathlib import Path
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "LearnGraph"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Security & JWT Authentication (Fail-fast: strictly required in environment)
    SECRET_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ENABLE_DEMO_ENDPOINTS: bool = True

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY", mode="after")
    @classmethod
    def validate_secrets_not_empty(cls, v: str, info) -> str:
        if not v or not str(v).strip():
            raise ValueError(
                f"{info.field_name} must be provided in the environment and cannot be empty."
            )
        return str(v).strip()

    # Database configuration (strictly read from env, falls back to SQLite for local development)
    DATABASE_URL: str = f"sqlite:///{BACKEND_DIR / 'learngraph.db'}"
    DB_POOL_SIZE: int = 15
    DB_MAX_OVERFLOW: int = 30

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if not v or not v.strip():
            return f"sqlite:///{BACKEND_DIR / 'learngraph.db'}"
        v = v.strip()
        if v.startswith("sqlite:///./"):
            relative_path = v[len("sqlite:///./") :]
            absolute_path = (BACKEND_DIR / relative_path).resolve()
            return f"sqlite:///{absolute_path}"
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg2://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
            v = v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    # File upload and storage backend settings
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    UPLOAD_DIR: str = str(BACKEND_DIR / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 15
    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [".pdf", ".png", ".jpg", ".jpeg"]
    ALLOWED_UPLOAD_TYPES: Union[List[str], str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]

    # Celery & Redis Task Queue
    REDIS_URL: Optional[str] = None
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: Optional[bool] = None

    @model_validator(mode="after")
    def sync_config(self) -> "Settings":
        if self.MAX_UPLOAD_SIZE_MB and self.MAX_UPLOAD_SIZE_BYTES == 15 * 1024 * 1024:
            self.MAX_UPLOAD_SIZE_BYTES = self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if self.REDIS_URL:
            if self.CELERY_BROKER_URL == "redis://localhost:6379/0":
                self.CELERY_BROKER_URL = self.REDIS_URL
            if self.CELERY_RESULT_BACKEND == "redis://localhost:6379/0":
                self.CELERY_RESULT_BACKEND = self.REDIS_URL
        if self.CELERY_TASK_ALWAYS_EAGER is None:
            self.CELERY_TASK_ALWAYS_EAGER = (
                self.ENVIRONMENT.lower() != "production" or not bool(self.REDIS_URL)
            )
        return self

    @field_validator("ALLOWED_UPLOAD_TYPES", mode="before")
    @classmethod
    def assemble_allowed_types(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["application/pdf", "image/jpeg", "image/png"]


    @field_validator("UPLOAD_DIR", mode="after")
    @classmethod
    def normalize_upload_dir(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        return str(p)

    # OCR Processing settings
    OCR_PROVIDER: str = "mock"  # "mock" or "paddleocr"
    OCR_LOW_CONFIDENCE_THRESHOLD: float = 0.6
    PADDLEOCR_LANG: str = "en"
    PADDLEOCR_USE_ANGLE_CLS: bool = True
    PADDLEOCR_USE_GPU: bool = False
    PADDLEOCR_USE_DOC_UNWARPING: bool = False
    PADDLEOCR_USE_DOC_ORIENTATION_CLASSIFY: bool = False
    PADDLEOCR_RENDER_SCALE: float = 2.0
    PADDLEOCR_BORDER_PADDING: int = 0

    # AI Evaluation Engine settings (local VLLM or mock)
    EVALUATOR_PROVIDER: str = "mock"  # "mock" or "vllm"
    VLLM_BASE_URL: str = "http://localhost:8001/v1"
    VLLM_MODEL: str = "default-model"
    VLLM_TIMEOUT_SECONDS: float = 30.0
    VLLM_API_KEY: Optional[str] = None
    VLLM_TEMPERATURE: float = 0.0
    ENABLE_EVALUATOR_FALLBACK: bool = True

    # Targeted Follow-up & Remediation Generation settings
    REMEDIATION_PROVIDER: str = "mock"


    # CORS configuration
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        defaults = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        origins = []
        if isinstance(v, str) and not v.startswith("["):
            origins = [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            origins = [str(i).strip() for i in v if str(i).strip()]
        for d in defaults:
            if d not in origins:
                origins.append(d)
        return origins

    model_config = SettingsConfigDict(
        env_file=[".env", str(BACKEND_DIR / ".env")],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
