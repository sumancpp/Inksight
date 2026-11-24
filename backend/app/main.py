from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.schemas.health import HealthResponse

# Initialize logging
setup_logging(debug=settings.DEBUG)

app = FastAPI(
    title="Inksight API",
    description="Inksight AI Diagnostic Platform API — Intelligent Student Answer Sheet Evaluation, Handwriting OCR, and Misconception Remediation",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

def _add_cors_headers(request: Request, response: JSONResponse) -> JSONResponse:
    """Helper ensuring CORS response headers are attached even during unhandled exceptions or error responses."""
    origin = request.headers.get("origin")
    allowed = (
        [str(o).rstrip("/") for o in settings.BACKEND_CORS_ORIGINS]
        if settings.BACKEND_CORS_ORIGINS
        else []
    )
    if origin and (origin.rstrip("/") in allowed or "*" in allowed):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# Request timing and logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = None
    try:
        response = await call_next(request)
        process_time_ms = (time.time() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({process_time_ms:.2f}ms)"
        )
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        return response
    except Exception as exc:
        process_time_ms = (time.time() - start_time) * 1000
        logger.error(
            f"{request.method} {request.url.path} -> 500 error ({process_time_ms:.2f}ms): {exc}",
            exc_info=True,
        )
        err_response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": 500,
                    "message": "An unexpected internal server error occurred.",
                    "details": str(exc) if settings.DEBUG else None,
                    "path": request.url.path,
                }
            },
        )
        err_response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        return _add_cors_headers(request, err_response)


# CORS middleware (added as outermost middleware to handle all responses including preflights)
cors_origins = list(settings.BACKEND_CORS_ORIGINS) if settings.BACKEND_CORS_ORIGINS else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
for default_origin in ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]:
    if default_origin not in cors_origins:
        cors_origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "path": request.url.path,
            }
        },
    )
    return _add_cors_headers(request, response)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    response = JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": 422,
                "message": "Validation error in request parameters or body.",
                "details": jsonable_encoder(exc.errors()),
                "path": request.url.path,
            }
        },
    )
    return _add_cors_headers(request, response)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": 500,
                "message": "An unexpected internal server error occurred.",
                "details": str(exc) if settings.DEBUG else None,
                "path": request.url.path,
            }
        },
    )
    return _add_cors_headers(request, response)


def auto_seed_demo_user() -> None:
    """
    Idempotently seeds the demo teacher users and initial data on application startup.
    Runs safely on every restart: if the demo user already exists, it does nothing.
    """
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    db = SessionLocal()
    try:
        # Check and create primary demo teacher: smith@learngraph.edu
        smith = db.query(User).filter(User.email == "smith@learngraph.edu").first()
        if not smith:
            logger.info("Auto-seeding demo teacher user: smith@learngraph.edu")
            smith = User(
                email="smith@learngraph.edu",
                full_name="Dr. Smith",
                role=UserRole.TEACHER.value,
                hashed_password=hash_password("teacher123"),
                is_active=True,
            )
            db.add(smith)
            db.commit()
            db.refresh(smith)
            logger.info(f"Successfully auto-seeded demo teacher smith@learngraph.edu (id={smith.id})")

        # Also create smith@inksight.edu for the Inksight rebrand
        smith_inksight = db.query(User).filter(User.email == "smith@inksight.edu").first()
        if not smith_inksight:
            logger.info("Auto-seeding demo teacher user: smith@inksight.edu")
            smith_inksight = User(
                email="smith@inksight.edu",
                full_name="Dr. Smith",
                role=UserRole.TEACHER.value,
                hashed_password=hash_password("teacher123"),
                is_active=True,
            )
            db.add(smith_inksight)
            db.commit()
            logger.info(f"Successfully auto-seeded demo teacher smith@inksight.edu (id={smith_inksight.id})")

        # If database has zero assessments, optionally seed initial cluster demo data
        from app.models.assessment import Assessment
        if db.query(Assessment).count() == 0:
            logger.info("Zero assessments detected in database. Seeding initial demo assessment and clusters...")
            try:
                from scripts.seed_cluster_demo import seed_cluster_demo
                seed_cluster_demo(db, force=True)
                logger.info("Successfully seeded initial demo assessment, topics, and misconception clusters.")
            except Exception as seed_err:
                logger.warning(f"Optional assessment seeding skipped/failed: {seed_err}")
    except Exception as exc:
        db.rollback()
        logger.error(f"Failed to auto-seed demo teacher user on startup: {exc}", exc_info=True)
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    auto_seed_demo_user()


# Root health check endpoint
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Root Health Check",
    description="Basic service liveness check.",
)
def root_health() -> HealthResponse:
    return HealthResponse(status="ok")


# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)
