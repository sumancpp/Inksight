import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.assessment import Assessment
from app.models.enums import SubmissionStatus, UserRole
from app.models.submission import Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.repositories.upload_repository import upload_repository
from app.services.storage_service import storage_service

# Small synthetic valid file payloads
SYNTHETIC_PDF = b"%PDF-1.5\n%synthetic test pdf content\n%%EOF\n"
SYNTHETIC_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00synthetic\xff\xd9"
SYNTHETIC_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
        full_name="Upload Student",
        email="student.upload@example.com",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    topic = LearningTopic(
        name="Upload Topic",
        description="Testing uploads",
    )
    db_session.add_all([student, topic])
    db_session.commit()

    assessment = Assessment(
        title="Upload Exam",
        description="Exam for testing uploads",
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



def test_upload_valid_pdf(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("answersheet.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "answersheet.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["file_size_bytes"] == len(SYNTHETIC_PDF)
    assert data["upload_status"] == "uploaded"
    assert data["submission_id"] == sample_submission.id
    assert "stored_filename" in data
    # Ensure internal filesystem path is not exposed
    assert "storage_path" not in data

    # Verify physical file existence in temp storage
    stored_path = temp_storage / data["stored_filename"]
    assert stored_path.exists()
    assert stored_path.read_bytes() == SYNTHETIC_PDF


def test_upload_valid_jpeg(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("page1.jpg", io.BytesIO(SYNTHETIC_JPEG), "image/jpeg")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "page1.jpg"
    assert data["content_type"] == "image/jpeg"
    assert data["file_size_bytes"] == len(SYNTHETIC_JPEG)


def test_upload_valid_png(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("diagram.png", io.BytesIO(SYNTHETIC_PNG), "image/png")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "diagram.png"
    assert data["content_type"] == "image/png"
    assert data["file_size_bytes"] == len(SYNTHETIC_PNG)


def test_download_uploaded_file(client: TestClient, sample_submission: Submission, temp_storage: Path):
    upload_res = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("scan.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert upload_res.status_code == 201
    upload_id = upload_res.json()["id"]

    # Metadata retrieval
    meta_res = client.get(f"/api/v1/answer-sheets/{upload_id}")
    assert meta_res.status_code == 200
    assert meta_res.json()["id"] == upload_id
    assert meta_res.json()["original_filename"] == "scan.pdf"

    # Download file
    download_res = client.get(f"/api/v1/answer-sheets/{upload_id}/file")
    assert download_res.status_code == 200
    assert download_res.content == SYNTHETIC_PDF
    assert download_res.headers["content-type"] == "application/pdf"


def test_missing_submission_returns_404(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        "/api/v1/submissions/99999/answer-sheets",
        files={"file": ("test.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"].lower()

    # Verify no file was created in storage
    assert len(list(temp_storage.glob("*"))) == 0


def test_missing_upload_returns_404(client: TestClient, sample_submission: Submission):
    meta_res = client.get("/api/v1/answer-sheets/99999")
    assert meta_res.status_code == 404

    file_res = client.get("/api/v1/answer-sheets/99999/file")
    assert file_res.status_code == 404


def test_unsupported_file_extension(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("answers.txt", io.BytesIO(b"simple text content"), "text/plain")},
    )
    assert response.status_code in (400, 415)
    assert "unsupported" in response.json()["error"]["message"].lower() or "invalid" in response.json()["error"]["message"].lower()
    assert len(list(temp_storage.glob("*"))) == 0


def test_mismatched_magic_bytes_signature(client: TestClient, sample_submission: Submission, temp_storage: Path):
    # File named .pdf with application/pdf header, but body is plain text
    fake_pdf = b"Plain text disguised as a PDF document"
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("corrupt.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert response.status_code in (400, 415)
    assert "signature" in response.json()["error"]["message"].lower()
    assert len(list(temp_storage.glob("*"))) == 0


def test_oversized_file_rejected_and_cleaned_up(
    client: TestClient, sample_submission: Submission, temp_storage: Path, monkeypatch
):
    # Set max limit to 100 bytes for test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 100)

    oversized_data = b"%PDF-1.5\n" + (b"X" * 500)
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("huge.pdf", io.BytesIO(oversized_data), "application/pdf")},
    )
    assert response.status_code in (400, 413)
    assert "exceeds maximum allowed size" in response.json()["error"]["message"].lower()

    # Verify partially written file was cleaned up
    assert len(list(temp_storage.glob("*"))) == 0


def test_upload_txt_file_rejected_with_400(client: TestClient, sample_submission: Submission, temp_storage: Path):
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("document.txt", io.BytesIO(b"some raw text"), "text/plain")},
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["error"]["message"].lower() or "extension" in response.json()["error"]["message"].lower()


def test_upload_oversized_file_rejected_with_400(client: TestClient, sample_submission: Submission, temp_storage: Path, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 15)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 15 * 1024 * 1024)

    # 16 MB fake file
    oversized_data = io.BytesIO(b"%PDF-1.5\n" + (b"0" * (16 * 1024 * 1024)))
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("large_20mb.pdf", oversized_data, "application/pdf")},
    )
    assert response.status_code == 400
    assert "exceeds maximum allowed size" in response.json()["error"]["message"].lower()


def test_upload_renamed_text_to_pdf_rejected_by_magic_with_400(client: TestClient, sample_submission: Submission, temp_storage: Path):
    text_content = b"This is a text file renamed to .pdf to bypass validation"
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("fake.pdf", io.BytesIO(text_content), "application/pdf")},
    )
    assert response.status_code == 400
    assert "signature" in response.json()["error"]["message"].lower()


def test_upload_renamed_exe_to_pdf_rejected_by_magic_with_400(client: TestClient, sample_submission: Submission, temp_storage: Path):
    exe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + (b"\x00" * 100)
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("malware.pdf", io.BytesIO(exe_bytes), "application/pdf")},
    )
    assert response.status_code == 400
    assert "signature" in response.json()["error"]["message"].lower()


def test_malware_scanner_called_on_upload(client: TestClient, sample_submission: Submission, temp_storage: Path, monkeypatch):
    from app.services.malware_scanner import malware_scanner
    called = []
    def mock_scan(file_bytes: bytes) -> bool:
        called.append(len(file_bytes))
        return True
    monkeypatch.setattr(malware_scanner, "scan_file", mock_scan)

    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("clean.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert response.status_code == 201
    assert len(called) > 0


def test_path_traversal_attempt_in_filename(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    traversal_name = "../../../../etc/passwd.pdf"
    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": (traversal_name, io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "passwd.pdf"
    stored_path = temp_storage / data["stored_filename"]
    assert stored_path.exists()
    assert stored_path.is_relative_to(temp_storage)


def test_cleanup_on_failed_database_persistence(
    client: TestClient, sample_submission: Submission, temp_storage: Path, monkeypatch
):
    def mock_create_failure(*args, **kwargs):
        raise RuntimeError("Simulated database failure during upload record creation")

    monkeypatch.setattr(upload_repository, "create_upload", mock_create_failure)

    response = client.post(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
        files={"file": ("rollback.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
    )
    assert response.status_code == 500

    # Ensure the uploaded file was cleaned up from storage
    assert len(list(temp_storage.glob("*"))) == 0


def test_list_submission_answer_sheets_pagination(
    client: TestClient, sample_submission: Submission, temp_storage: Path
):
    # Upload 3 files
    for i in range(3):
        client.post(
            f"/api/v1/submissions/{sample_submission.id}/answer-sheets",
            files={"file": (f"sheet_{i}.pdf", io.BytesIO(SYNTHETIC_PDF), "application/pdf")},
        )

    # Page 1: limit 2, offset 0
    res_p1 = client.get(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets?limit=2&offset=0"
    )
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert data_p1["total"] == 3
    assert len(data_p1["items"]) == 2
    assert data_p1["limit"] == 2
    assert data_p1["offset"] == 0

    # Page 2: limit 2, offset 2
    res_p2 = client.get(
        f"/api/v1/submissions/{sample_submission.id}/answer-sheets?limit=2&offset=2"
    )
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert data_p2["total"] == 3
    assert len(data_p2["items"]) == 1
    assert data_p2["limit"] == 2
    assert data_p2["offset"] == 2
