import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import ProposalStatus, QuestionType, SubmissionStatus, UploadStatus, UserRole
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.services.answer_sheet_inference_service import answer_sheet_inference_service
from tests.conftest import auth_headers_for_user


@pytest.fixture
def inference_test_setup(client: TestClient, db_session: Session):
    teacher = User(
        full_name="Prof. Turing",
        email="turing@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="Ada Lovelace",
        email="ada@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(
        name="Computer Networks",
        description="OSI, TCP/IP, Routing, Subnetting",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Zero QP Assessment",
        description="Assessment without predefined questions",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status=SubmissionStatus.SUBMITTED.value,
    )
    db_session.add(submission)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="DocScanner_Exam.pdf",
        stored_filename="docscanner_exam_uuid.pdf",
        storage_path="/tmp/docscanner_exam_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=2048,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    # Create multi-page OCR extraction text with college headers and student CN exam answers
    cn_text = """
    OMDAYAL GROUP OF INSTITUTIONS
    DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING
    MIDTERM EXAMINATION 2026
    Roll No: 123456789   Reg No: 987654321
    Invigilator Signature: Approved

    Question 1:
    Hamming distance between code words 110010 and 100110 is 2.

    Question 2:
    Stop-and-Wait protocol efficiency:
    Tt = 1000 * 8 / 8000 = 1 sec
    Tp = 0.1 sec
    Efficiency = Tt / (Tt + 2*Tp) = 1 / (1 + 0.2) = 83.33%

    Question 3:
    Given IP addresses and subnet mask 255.255.255.240 (/28):
    203.165.100.8 belongs to subnet 203.165.100.0/28
    203.165.100.17 belongs to subnet 203.165.100.16/28
    203.165.100.28 belongs to subnet 203.165.100.16/28
    203.165.100.35 belongs to subnet 203.165.100.32/28

    Question 4:
    Distance Vector Routing:
    Uses Bellman-Ford algorithm Dx(y) = min_v { c(x,v) + Dv(y) }.
    Each node periodically sends its routing table to its neighbors.

    Question 5:
    OSI vs TCP/IP models:
    OSI has 7 layers: Physical, Data Link, Network, Transport, Session, Presentation, Application.
    TCP/IP has 4 layers: Link, Internet, Transport, Application.
    """

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="paddle_ocr",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text=cn_text,
        confidence=0.92,
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "OMDAYAL GROUP OF INSTITUTIONS", "confidence": 0.95},
            {"segment_id": 2, "page": 1, "text": "Roll No: 123456789 Reg No: 987654321", "confidence": 0.95},
            {"segment_id": 3, "page": 1, "text": "Tt = 1 sec, Tp = 0.1 sec, Efficiency = 83.33%", "confidence": 0.90},
            {"segment_id": 4, "page": 2, "text": "203.165.100.8 belongs to subnet 203.165.100.0/28", "confidence": 0.88},
        ],
    )
    db_session.add(extraction)
    db_session.commit()

    # Pre-populate some clutter unassigned proposed answers to verify they get cleaned
    unassigned_p1 = ProposedAnswer(
        upload_id=upload.id,
        submission_id=submission.id,
        ocr_extraction_id=extraction.id,
        question_id=None,
        proposed_text="OMDAYAL GROUP OF INSTITUTIONS",
        confidence=0.95,
        status="unmatched",
        rejection_reason="NO_QUESTION_NUMBER_DETECTED",
    )
    unassigned_p2 = ProposedAnswer(
        upload_id=upload.id,
        submission_id=submission.id,
        ocr_extraction_id=extraction.id,
        question_id=None,
        proposed_text="Roll No: 123456789 Reg No: 987654321",
        confidence=0.95,
        status="unmatched",
        rejection_reason="NO_QUESTION_NUMBER_DETECTED",
    )
    db_session.add_all([unassigned_p1, unassigned_p2])
    db_session.commit()

    client.headers.update(auth_headers_for_user(teacher))

    return {
        "teacher": teacher,
        "student": student,
        "assessment": assessment,
        "submission": submission,
        "upload": upload,
        "extraction": extraction,
    }


def test_filter_header_metadata():
    raw_text = """
    OMDAYAL GROUP OF INSTITUTIONS
    DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING
    MIDTERM EXAMINATION 2026
    Roll No: 123456789   Reg No: 987654321
    Invigilator Signature: Approved
    Date: 2026-11-05
    Page 1 of 6

    Question 1:
    What is Stop-and-Wait protocol efficiency?
    Efficiency = 83.33%
    """
    cleaned = answer_sheet_inference_service.filter_header_metadata(raw_text)
    assert "OMDAYAL" not in cleaned
    assert "Roll No" not in cleaned
    assert "Invigilator" not in cleaned
    assert "Page 1 of 6" not in cleaned
    assert "Stop-and-Wait" in cleaned
    assert "Efficiency = 83.33%" in cleaned


def test_infer_questions_endpoint(client: TestClient, db_session: Session, inference_test_setup):
    upload = inference_test_setup["upload"]
    submission = inference_test_setup["submission"]

    # Verify clutter proposals exist before inference
    clutter_count_before = (
        db_session.query(ProposedAnswer)
        .filter(ProposedAnswer.upload_id == upload.id, ProposedAnswer.question_id.is_(None))
        .count()
    )
    assert clutter_count_before == 2

    # Call infer-questions endpoint
    response = client.post(f"/api/v1/answer-sheets/{upload.id}/infer-questions")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["upload_id"] == upload.id
    assert data["submission_id"] == submission.id
    assert data["mode"] == "inferred_questions"
    assert data["total_inferred"] >= 4

    # Assert clutter proposals were deleted
    clutter_count_after = (
        db_session.query(ProposedAnswer)
        .filter(ProposedAnswer.upload_id == upload.id, ProposedAnswer.question_id.is_(None))
        .count()
    )
    assert clutter_count_after == 0

    # Assert structured items
    items = data["items"]
    first_item = items[0]
    assert first_item["question_number"] == 1
    assert "inferred_question" in first_item and len(first_item["inferred_question"]) > 10
    assert "student_answer" in first_item
    assert "concept_name" in first_item
    assert first_item["marks_awarded"] > 0
    assert first_item["question_id"] is not None
    assert first_item["finding_id"] is not None

    # Assert Question records were created in DB
    questions = db_session.query(Question).filter(Question.assessment_id == inference_test_setup["assessment"].id).all()
    assert len(questions) >= 4


def test_update_inferred_question_endpoint(client: TestClient, db_session: Session, inference_test_setup):
    upload = inference_test_setup["upload"]

    # Run inference first
    inf_res = client.post(f"/api/v1/answer-sheets/{upload.id}/infer-questions")
    assert inf_res.status_code == 200
    inf_data = inf_res.json()
    first_q_id = inf_data["items"][0]["question_id"]

    # Teacher updates inferred question prompt and expected answer
    patch_payload = {
        "inferred_question": "Revised Prompt: Calculate the exact Stop-and-Wait protocol efficiency and throughput.",
        "expected_answer": "Tt = 1s, Tp = 0.1s, Efficiency = 83.33%, Throughput = 800 bytes/sec.",
        "re_evaluate": True,
    }
    update_res = client.patch(
        f"/api/v1/answer-sheets/{upload.id}/inferred-questions/{first_q_id}",
        json=patch_payload,
    )
    assert update_res.status_code == 200, update_res.text
    updated_item = update_res.json()
    assert updated_item["inferred_question"] == patch_payload["inferred_question"]
    assert updated_item["expected_answer"] == patch_payload["expected_answer"]

    # Check database question prompt was updated
    q_db = db_session.query(Question).filter(Question.id == first_q_id).first()
    assert q_db is not None
    assert q_db.prompt == patch_payload["inferred_question"]
    assert q_db.expected_answer == patch_payload["expected_answer"]


def test_rbac_student_cannot_infer_questions(client: TestClient, inference_test_setup):
    upload = inference_test_setup["upload"]
    student = inference_test_setup["student"]

    # Switch client to student role
    client.headers.update(auth_headers_for_user(student))

    response = client.post(f"/api/v1/answer-sheets/{upload.id}/infer-questions")
    assert response.status_code == 403
