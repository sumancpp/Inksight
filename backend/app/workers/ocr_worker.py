"""
Celery worker tasks for background OCR extraction and AI diagnostic evaluation.
"""
import asyncio
import concurrent.futures
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.enums import UploadStatus
from app.repositories.submission_repository import submission_repository
from app.repositories.upload_repository import upload_repository
from app.services.evaluation_service import evaluation_service
from app.services.ocr_service import ocr_processing_service


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


def dispatch_ocr_and_evaluate(submission_id: int):
    """
    Dispatches task to Celery worker via Redis broker.
    If Redis broker is unreachable, safely falls back to eager in-memory execution.
    """
    try:
        return process_ocr_and_evaluate_task.delay(submission_id)
    except Exception as exc:
        logger.warning(
            f"[Celery] Redis broker unavailable ({exc}). Executing eagerly in-memory."
        )
        orig_backend = celery_app.conf.result_backend
        orig_eager = celery_app.conf.task_always_eager
        celery_app.conf.result_backend = "cache+memory://"
        celery_app.conf.task_always_eager = True
        try:
            return process_ocr_and_evaluate_task.apply(args=[submission_id])
        finally:
            celery_app.conf.result_backend = orig_backend
            celery_app.conf.task_always_eager = orig_eager
