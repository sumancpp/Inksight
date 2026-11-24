"""
Celery worker tasks for background OCR extraction and AI diagnostic evaluation.
"""
import asyncio
import concurrent.futures
import threading
import uuid
from types import SimpleNamespace
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks
import redis as redis_lib

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.enums import UploadStatus
from app.repositories.submission_repository import submission_repository
from app.repositories.upload_repository import upload_repository
from app.services.evaluation_service import evaluation_service
from app.services.ocr_service import ocr_processing_service

_LOCAL_TASK_RESULTS: Dict[str, Dict[str, Any]] = {}
_LOCAL_TASK_LOCK = threading.Lock()


def get_local_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    with _LOCAL_TASK_LOCK:
        entry = _LOCAL_TASK_RESULTS.get(task_id)
        return dict(entry) if entry is not None else None


def _set_local_task_status(task_id: str, payload: Dict[str, Any]) -> None:
    with _LOCAL_TASK_LOCK:
        _LOCAL_TASK_RESULTS[task_id] = payload


def _safe_update_state(task_self, state: str, meta: Dict[str, Any]) -> None:
    try:
        task_self.update_state(state=state, meta=meta)
    except Exception as exc:
        logger.debug(f"[Celery] State update skipped: {exc}")


def run_async_coro(coro):
    """
    Safely runs an async coroutine from synchronous Celery task code,
    handling both standalone threads and active asyncio event loops (e.g. eager mode / TestClient).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


@celery_app.task(bind=True, name="process_ocr_and_evaluate_task")
def process_ocr_and_evaluate_task(self, submission_id: int) -> Dict[str, Any]:
    """
    Celery background worker task for OCR processing and AI evaluation.
    1. Loads all uploads for the submission.
    2. Runs OCR for any unextracted answer sheets.
    3. Runs AI diagnostic evaluation for teacher-approved answers.
    4. Returns evaluation findings.
    """
    task_id = self.request.id or "eager"
    logger.info(f"[Celery] Worker started task={task_id} for submission_id={submission_id}")
    _safe_update_state(
        self,
        state="STARTED",
        meta={"step": "Initialising background OCR & evaluation...", "submission_id": submission_id},
    )

    # In test/dev environment, check dependency overrides if present
    from app.main import app
    from app.core.database import get_db

    is_override = get_db in app.dependency_overrides
    if is_override:
        override = app.dependency_overrides[get_db]
        res = override()
        db = next(res) if hasattr(res, "__next__") else res
    else:
        db = SessionLocal()

    try:
        sub = submission_repository.get_by_id(db, submission_id=submission_id)
        if not sub:
            raise ValueError(f"Submission #{submission_id} not found.")

        # 1. Process any pending uploads
        uploads, _ = upload_repository.get_multi_by_submission(db=db, submission_id=submission_id, limit=1000)
        for u in uploads:
            if u.upload_status in (UploadStatus.UPLOADED, UploadStatus.QUEUED, UploadStatus.PROCESSING):
                _safe_update_state(
                    self,
                    state="STARTED",
                    meta={
                        "step": f"Processing OCR on upload #{u.id} ({u.original_filename})...",
                        "submission_id": submission_id,
                    },
                )
                run_async_coro(ocr_processing_service.process_upload(u.id))

        # 2. Run diagnostic evaluation
        _safe_update_state(
            self,
            state="STARTED",
            meta={"step": "Executing AI diagnostic evaluation...", "submission_id": submission_id},
        )
        eval_summary = run_async_coro(
            evaluation_service.evaluate_submission(db=db, submission_id=submission_id)
        )

        summary_dict = eval_summary.model_dump(mode="json")
        all_findings = []
        for run in summary_dict.get("runs", []):
            for finding in run.get("findings", []):
                all_findings.append(finding)

        result = {
            "submission_id": submission_id,
            "status": "SUCCESS",
            "total_runs": eval_summary.total_runs,
            "runs": summary_dict.get("runs", []),
            "findings": all_findings,
        }
        logger.info(f"[Celery] Task={task_id} completed successfully for submission_id={submission_id}")
        return result

    except Exception as exc:
        logger.error(f"[Celery] Task={task_id} failed for submission_id={submission_id}: {exc}")
        _safe_update_state(
            self,
            state="FAILURE",
            meta={"error": str(exc), "submission_id": submission_id},
        )
        raise
    finally:
        if not is_override:
            db.close()


def run_ocr_and_evaluate_local(task_id: str, submission_id: int) -> Dict[str, Any]:
    """
    Executes OCR & evaluation in-process (eagerly or via FastAPI BackgroundTasks)
    and records status/results in _LOCAL_TASK_RESULTS so task-status polling resolves.
    """
    _set_local_task_status(
        task_id,
        {
            "status": "STARTED",
            "ready": False,
            "successful": None,
            "result": {"step": "Running OCR & AI evaluation...", "submission_id": submission_id},
            "findings": None,
            "error": None,
        },
    )
    orig_backend = celery_app.conf.result_backend
    orig_eager = celery_app.conf.task_always_eager
    celery_app.conf.result_backend = "cache+memory://"
    celery_app.conf.task_always_eager = True
    try:
        async_res = process_ocr_and_evaluate_task.apply(args=[submission_id], task_id=task_id)
        result = async_res.result
        if isinstance(result, Exception):
            raise result
        findings = result.get("findings") if isinstance(result, dict) else None
        _set_local_task_status(
            task_id,
            {
                "status": "SUCCESS",
                "ready": True,
                "successful": True,
                "result": result,
                "findings": findings,
                "error": None,
            },
        )
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        logger.error(f"[LocalWorker] Task={task_id} failed for submission_id={submission_id}: {exc}")
        _set_local_task_status(
            task_id,
            {
                "status": "FAILURE",
                "ready": True,
                "successful": False,
                "result": None,
                "findings": None,
                "error": str(exc),
            },
        )
        return {"status": "FAILURE", "error": str(exc)}
    finally:
        celery_app.conf.result_backend = orig_backend
        celery_app.conf.task_always_eager = orig_eager


def dispatch_ocr_and_evaluate(
    submission_id: int,
    background_tasks: Optional[BackgroundTasks] = None,
):
    """
    Dispatches task to Celery worker via Redis broker.
    - If CELERY_TASK_ALWAYS_EAGER is True: runs synchronously and stores local status.
    - If Redis broker is unreachable: falls back to FastAPI BackgroundTasks (or synchronous).
    """
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) or celery_app.conf.task_always_eager:
        task_id = str(uuid.uuid4())
        run_ocr_and_evaluate_local(task_id, submission_id)
        return SimpleNamespace(id=task_id)

    try:
        client = redis_lib.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=1.0)
        client.ping()
        return process_ocr_and_evaluate_task.delay(submission_id)
    except Exception as exc:
        logger.warning(
            f"[Celery] Redis broker unavailable ({exc}). Falling back to FastAPI BackgroundTasks."
        )
        task_id = str(uuid.uuid4())
        if background_tasks is not None:
            _set_local_task_status(
                task_id,
                {
                    "status": "PENDING",
                    "ready": False,
                    "successful": None,
                    "result": {"step": "Queued in local background worker...", "submission_id": submission_id},
                    "findings": None,
                    "error": None,
                },
            )
            background_tasks.add_task(run_ocr_and_evaluate_local, task_id, submission_id)
        else:
            run_ocr_and_evaluate_local(task_id, submission_id)
        return SimpleNamespace(id=task_id)
