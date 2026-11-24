"""
Celery application initialization and configuration.
"""
from celery import Celery
from app.core.config import settings

is_eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
broker_url = "memory://" if is_eager else settings.CELERY_BROKER_URL
result_backend = "cache+memory://" if is_eager else settings.CELERY_RESULT_BACKEND

celery_app = Celery(
    "inksight_worker",
    broker=broker_url,
    backend=result_backend,
    include=["app.workers.ocr_worker"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=is_eager,
    task_eager_propagates=True,
    task_store_eager_result=True,
)
