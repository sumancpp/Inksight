import asyncio
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


from app.core.config import settings
from app.models.assessment import Assessment
from app.models.enums import (
    InvalidStateTransitionError,
    SubmissionStatus,
    UploadStatus,
    UserRole,
    validate_upload_transition,
)
from app.models.submission import AnswerSheetUpload, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.repositories.upload_repository import upload_repository
from app.services.ocr.base import OCRAdapterError
from app.services.ocr.mock_adapter import MockOCRAdapter
from app.services.storage_service import storage_service

SYNTHETIC_PDF = b"%PDF-1.5\n%Synthetic exam answer sheet for OCR pipeline tests\n%%EOF\n"
SYNTHETIC_EMPTY_TRIGGER_PDF = b"%PDF-1.5\nMOCK_TRIGGER_EMPTY\n%%EOF\n"
SYNTHETIC_LOW_CONF_PDF = b"%PDF-1.5\nMOCK_TRIGGER_LOW_CONFIDENCE\n%%EOF\n"
SYNTHETIC_ERROR_TRIGGER_PDF = b"%PDF-1.5\nMOCK_TRIGGER_ERROR\n%%EOF\n"
SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00synthetic\xff\xd9"
SYNTHETIC_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def ensure_mock_ocr_in_mock_pipeline_tests(monkeypatch):
    """Explicitly use mock OCR adapter for mock trigger tests."""
    monkeypatch.setattr(settings, "OCR_PROVIDER", "mock")


@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    """Isolate uploads directory to a clean temp folder for testing."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage_service, "_upload_dir_setting", str(upload_dir))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    return upload_dir


@pytest.fixture
def sample_submission(client: TestClient, db_session: Session) -> Submission:
    """Creates a sample student and assessment with a submission."""
    student = User(
        full_name="OCR Student",
        email="ocr.student@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    topic = LearningTopic(
        name="Physics Topic",
        description="Testing OCR",
    )
    db_session.add_all([student, topic])
    db_session.commit()

    assessment = Assessment(
        title="Physics Quiz",
        description="Quiz for OCR testing",
        created_by=student.id,
    )
    db_session.add(assessment)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status=SubmissionStatus.DRAFT.value,
    )
    db_session.add(submission)
    db_session.commit()
    db_session.refresh(submission)

    from tests.conftest import auth_headers_for_user
    client.headers.update(auth_headers_for_user(student))
    return submission


def test_mock_adapter_direct_extraction(tmp_path: Path):
    async def _run():
        adapter = MockOCRAdapter()
        test_file = tmp_path / "test_sheet.pdf"
        test_file.write_bytes(SYNTHETIC_PDF)

        result = await adapter.extract(test_file)
        assert result.provider_name == "mock_ocr_provider"
        assert "derivative" in result.extracted_text.lower()
        assert len(result.structured_segments) >= 2
        assert result.confidence is not None and result.confidence >= 0.8
        assert result.error_code is None

    asyncio.run(_run())


def test_mock_adapter_deterministic_triggers(tmp_path: Path):
    async def _run():
        adapter = MockOCRAdapter()

        # Empty trigger
        f_empty = tmp_path / "empty.pdf"
        f_empty.write_bytes(SYNTHETIC_EMPTY_TRIGGER_PDF)
        res_empty = await adapter.extract(f_empty)
        assert res_empty.extracted_text == ""
        assert res_empty.confidence == 0.0

        # Low confidence trigger
        f_low = tmp_path / "low.pdf"
        f_low.write_bytes(SYNTHETIC_LOW_CONF_PDF)
        res_low = await adapter.extract(f_low)
        assert res_low.confidence == 0.35

        # Error trigger
        f_err = tmp_path / "err.pdf"
        f_err.write_bytes(SYNTHETIC_ERROR_TRIGGER_PDF)
        with pytest.raises(OCRAdapterError) as exc_info:
            await adapter.extract(f_err)
        assert exc_info.value.error_code == "ADAPTER_FAILURE"

    asyncio.run(_run())



def test_invalid_state_transitions():
    # Valid transitions should pass
    validate_upload_transition(UploadStatus.UPLOADED, UploadStatus.QUEUED)
    validate_upload_transition(UploadStatus.QUEUED, UploadStatus.PROCESSING)
    validate_upload_transition(UploadStatus.PROCESSING, UploadStatus.EXTRACTED)
    validate_upload_transition(UploadStatus.PROCESSING, UploadStatus.NEEDS_REVIEW)
    validate_upload_transition(UploadStatus.PROCESSING, UploadStatus.FAILED)
    validate_upload_transition(UploadStatus.EXTRACTED, UploadStatus.QUEUED)
    validate_upload_transition(UploadStatus.FAILED, UploadStatus.QUEUED)

    # Invalid transitions must raise InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        validate_upload_transition(UploadStatus.PROCESSING, UploadStatus.UPLOADED)

    with pytest.raises(InvalidStateTransitionError):
        validate_upload_transition(UploadStatus.UPLOADED, UploadStatus.EXTRACTED)

    with pytest.raises(InvalidStateTransitionError):
        validate_upload_transition(UploadStatus.FAILED, UploadStatus.PROCESSING)


def test_process_valid_upload_success(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    # 1. Upload sheet
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("physics.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # 2. Trigger processing (TestClient runs background tasks before returning)
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202
    assert process_res.json()["upload_id"] == upload_id

    # 3. Check status
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["upload_status"] == "extracted"
    assert status_data["has_extraction"] is True
    assert status_data["latest_error_code"] is None

    # 4. Check extraction content
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    extract_data = extract_res.json()
    assert extract_data["upload_id"] == upload_id
    assert extract_data["provider_name"] == "mock_ocr_provider"
    assert extract_data["processing_status"] == "extracted"
    assert extract_data["confidence"] >= 0.8
    assert "derivative" in extract_data["extracted_text"].lower()
    assert len(extract_data["structured_segments"]) >= 2
    assert extract_data["error_code"] is None


def test_empty_extraction_routes_to_needs_review(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("empty.pdf", io.BytesIO(SYNTHETIC_EMPTY_TRIGGER_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Process
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    # Status should be needs_review
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "needs_review"
    assert status_res.json()["latest_error_code"] == "EMPTY_EXTRACTION"

    # Extraction record exists
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    assert extract_res.json()["processing_status"] == "needs_review"
    assert extract_res.json()["error_code"] == "EMPTY_EXTRACTION"


def test_low_confidence_routes_to_needs_review(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("low_conf.pdf", io.BytesIO(SYNTHETIC_LOW_CONF_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Process
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "needs_review"
    assert status_res.json()["latest_error_code"] == "LOW_CONFIDENCE"

    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    assert extract_res.json()["confidence"] == 0.35
    assert extract_res.json()["error_code"] == "LOW_CONFIDENCE"


def test_missing_stored_file_causes_safe_failure(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("missing.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    upload_id = upload_data["id"]

    # Delete physical file from storage to simulate file loss
    stored_path = temp_storage / upload_data["stored_filename"]
    assert stored_path.exists()
    stored_path.unlink()

    # Process
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    # Status must be failed
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "failed"
    assert status_res.json()["latest_error_code"] == "FILE_INACCESSIBLE"


def test_adapter_failure_handled_safely(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("fail.pdf", io.BytesIO(SYNTHETIC_ERROR_TRIGGER_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Process
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    # Status must be failed with safe error code
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "failed"
    assert status_res.json()["latest_error_code"] == "ADAPTER_FAILURE"


def test_duplicate_processing_rejected(
    client: TestClient, sample_submission: Submission, db_session: Session, temp_storage: Path
):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("concurrent.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Manually transition status to PROCESSING in database to simulate an active job
    upload_obj = upload_repository.get_by_id(db=db_session, upload_id=upload_id)
    upload_repository.update_status(db=db_session, db_obj=upload_obj, new_status=UploadStatus.PROCESSING)

    # Attempt to trigger processing again
    res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert res.status_code == 409
    assert "already being processed" in res.json()["error"]["message"].lower()


def test_missing_endpoints_404(client: TestClient, sample_submission: Submission, temp_storage: Path):
    # Non-existent upload
    assert client.post("/api/v1/answer-sheets/99999/process").status_code == 404
    assert client.get("/api/v1/answer-sheets/99999/processing-status").status_code == 404
    assert client.get("/api/v1/answer-sheets/99999/extraction").status_code == 404

    # Upload exists but not yet processed -> extraction returns 404
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("unprocessed.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    upload_id = upload_res.json()["id"]
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 404
    assert "not found or not yet processed" in extract_res.json()["error"]["message"].lower()


def test_extraction_404_while_in_processing_state(
    client: TestClient, sample_submission: Submission, db_session: Session, temp_storage: Path
):
    """Verifies that polling extraction while status is PROCESSING returns 404 with current status."""
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("in_progress.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Transition upload to PROCESSING to simulate active background OCR job
    upload_obj = upload_repository.get_by_id(db=db_session, upload_id=upload_id)
    upload_repository.update_status(db=db_session, db_obj=upload_obj, new_status=UploadStatus.PROCESSING)

    # Check status endpoint
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "processing"
    assert status_res.json()["has_extraction"] is False

    # Attempting to fetch extraction before completion returns 404 with explicit status
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 404
    error_msg = extract_res.json()["error"]["message"]
    assert "not found or not yet processed" in error_msg.lower()
    assert "processing" in error_msg.lower()


def test_process_valid_jpeg_answer_sheet(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    """Verifies that an uploaded JPEG answer sheet processes through OCR and returns extraction."""
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("page1.jpeg", io.BytesIO(SYNTHETIC_JPEG), "image/jpeg")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Trigger OCR processing
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    # Polling status endpoint
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "extracted"
    assert status_res.json()["has_extraction"] is True

    # Retrieve extraction
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    data = extract_res.json()
    assert data["upload_id"] == upload_id
    assert len(data["structured_segments"]) >= 1


def test_process_valid_png_answer_sheet(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    """Verifies that an uploaded PNG answer sheet processes through OCR and returns extraction."""
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("diagram.png", io.BytesIO(SYNTHETIC_PNG), "image/png")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Trigger OCR processing
    process_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert process_res.status_code == 202

    # Polling status endpoint
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    assert status_res.json()["upload_status"] == "extracted"
    assert status_res.json()["has_extraction"] is True

    # Retrieve extraction
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    data = extract_res.json()
    assert data["upload_id"] == upload_id
    assert len(data["structured_segments"]) >= 1


def test_processing_status_page_progress_reporting(
    client: TestClient, sample_submission: Submission, db_session: Session, temp_storage: Path
):
    """Verifies that /processing-status returns total_pages, pages_completed, and progress_percent."""
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("test.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Initially progress is 0
    status_res = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "total_pages" in status_data
    assert "pages_completed" in status_data
    assert "progress_percent" in status_data

    # Update progress in DB to simulate active background processing
    upload = upload_repository.get_by_id(db_session, upload_id)
    assert upload is not None
    upload_repository.update_progress(db_session, upload, pages_completed=15, total_pages=50)

    status_res2 = client.get(f"/api/v1/answer-sheets/{upload_id}/processing-status")
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    assert status_data2["total_pages"] == 50
    assert status_data2["pages_completed"] == 15
    assert status_data2["progress_percent"] == 30.0


def test_retrigger_processing_with_force_flag(
    client: TestClient, sample_submission: Submission, db_session: Session, temp_storage: Path
):
    """
    Verifies that re-triggering processing on an in-progress upload:
    - Fails with 409 Conflict when force is False (default)
    - Succeeds with 202 Accepted when force=True
    """
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("test.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Mark as PROCESSING manually to simulate stalled/long-running task
    upload = upload_repository.get_by_id(db_session, upload_id)
    assert upload is not None
    upload_repository.update_status(db_session, upload, UploadStatus.PROCESSING)

    # Calling process without force fails
    conflict_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process")
    assert conflict_res.status_code == 409

    # Calling process with force=true succeeds
    force_res = client.post(f"/api/v1/answer-sheets/{upload_id}/process?force=true")
    assert force_res.status_code == 202
    assert force_res.json()["status"] in ["queued", "processing"]


def test_extraction_endpoint_includes_math_detection_and_quality_warnings(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    """Verifies that the extraction response includes has_math_content and quality_warnings."""
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("page1.jpeg", io.BytesIO(SYNTHETIC_JPEG), "image/jpeg")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Process
    client.post(f"/api/v1/answer-sheets/{upload_id}/process")

    # Extract
    extract_res = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction")
    assert extract_res.status_code == 200
    data = extract_res.json()
    assert "has_math_content" in data
    assert isinstance(data["has_math_content"], bool)
    assert "quality_warnings" in data
    assert isinstance(data["quality_warnings"], list)


