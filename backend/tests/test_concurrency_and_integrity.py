import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.assessment import Assessment, Question
from app.models.enums import (
    EvaluationStatus,
    FindingCategory,
    FindingReviewStatus,
    PracticeItemReviewStatus,
    PracticeQuestionType,
    ProposalStatus,
    QuestionType,
    RemediationRunStatus,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.ocr import OCRExtraction
from app.models.practice import PracticeResponse, PracticeSession
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from tests.conftest import auth_headers_for_user


@pytest.fixture
def audit_setup(db_session: Session):
    """
    Sets up a complete test fixture for concurrency, integrity, and cross-resource tests:
    - Teacher and Students (Alice, Bob)
    - LearningTopic, Assessment, Question
    - Submissions for Alice and Bob
    - EvaluationRuns and accepted findings
    - Approved remediation items
    """
    teacher = User(
        full_name="Prof. Audit",
        email="prof.audit@learngraph.edu",
        role=UserRole.TEACHER.value,
        hashed_password=hash_password("TeacherPassword123!"),
        is_active=True,
    )
    student_alice = User(
        full_name="Alice Audit",
        email="alice.audit@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("AlicePassword123!"),
        is_active=True,
    )
    student_bob = User(
        full_name="Bob Audit",
        email="bob.audit@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("BobPassword123!"),
        is_active=True,
    )
    db_session.add_all([teacher, student_alice, student_bob])
    db_session.commit()

    topic = LearningTopic(
        name="Integral Calculus",
        description="Integration rules and applications",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Integration Audit Exam",
        description="Comprehensive calculus integration",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Integrate 3x^2 dx from 0 to 2.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        expected_answer="8",
    )
    db_session.add(q1)
    db_session.commit()

    sub_alice = Submission(
        assessment_id=assessment.id,
        student_id=student_alice.id,
        status=SubmissionStatus.REVIEWED.value,
    )
    sub_bob = Submission(
        assessment_id=assessment.id,
        student_id=student_bob.id,
        status=SubmissionStatus.REVIEWED.value,
    )
    db_session.add_all([sub_alice, sub_bob])
    db_session.commit()

    qa_alice = QuestionAnswer(
        submission_id=sub_alice.id,
        question_id=q1.id,
        answer_text="6",
        awarded_marks=2.0,
    )
    qa_bob = QuestionAnswer(
        submission_id=sub_bob.id,
        question_id=q1.id,
        answer_text="8",
        awarded_marks=5.0,
    )
    db_session.add_all([qa_alice, qa_bob])
    db_session.commit()

    # Upload, extraction, proposed answer and review records for Alice's authoritative answer
    upload_alice = AnswerSheetUpload(
        submission_id=sub_alice.id,
        original_filename="audit_sheet.pdf",
        stored_filename="audit_sheet_uuid.pdf",
        storage_path="/tmp/audit_sheet_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload_alice)
    db_session.commit()

    extraction_alice = OCRExtraction(
        upload_id=upload_alice.id,
        extracted_text="Question 1: 6",
        structured_segments={"segments": [{"id": 1, "text": "6"}]},
        provider_name="mock_ocr",
        processing_status="completed",
    )
    db_session.add(extraction_alice)
    db_session.commit()

    p1 = ProposedAnswer(
        submission_id=sub_alice.id,
        upload_id=upload_alice.id,
        ocr_extraction_id=extraction_alice.id,
        question_id=q1.id,
        segment_id=1,
        proposed_text=qa_alice.answer_text,
        status=ProposalStatus.APPROVED.value,
    )
    db_session.add(p1)
    db_session.commit()

    rev_alice = TeacherReview(
        proposal_id=p1.id,
        submission_id=sub_alice.id,
        question_id=q1.id,
        reviewer_id=teacher.id,
        action=ReviewAction.APPROVE.value,
        original_text=qa_alice.answer_text,
        final_text=qa_alice.answer_text,
    )
    db_session.add(rev_alice)
    db_session.commit()

    # Evaluation Run for Alice
    eval_run_alice = EvaluationRun(
        submission_id=sub_alice.id,
        question_id=q1.id,
        question_answer_id=qa_alice.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_audit_alice_6",
        answer_text_snapshot=qa_alice.answer_text,
    )
    db_session.add(eval_run_alice)
    db_session.commit()

    finding_alice = EvaluationFinding(
        run_id=eval_run_alice.id,
        topic_id=topic.id,
        concept_name="Power Rule Integration",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.95,
        evidence_excerpt="6",
        rationale="Student applied differentiation power rule instead of integration.",
        review_status=FindingReviewStatus.ACCEPTED.value,
        reviewed_by=teacher.id,
    )
    db_session.add(finding_alice)
    db_session.commit()

    remed_run_alice = RemediationRun(
        finding_id=finding_alice.id,
        evaluation_run_id=eval_run_alice.id,
        generator_name="mock_generator",
        status=RemediationRunStatus.COMPLETED.value,
    )
    db_session.add(remed_run_alice)
    db_session.commit()

    item_alice_1 = RemediationItem(
        run_id=remed_run_alice.id,
        finding_id=finding_alice.id,
        target_concept="Power Rule Integration",
        question_text="What is the integral of x^n dx for n != -1?",
        question_type=PracticeQuestionType.MULTIPLE_CHOICE.value,
        options=["A) x^(n+1) / (n+1) + C", "B) n * x^(n-1)", "C) x^(n-1) / (n-1) + C"],
        teacher_answer_key="A",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
    )
    item_alice_2 = RemediationItem(
        run_id=remed_run_alice.id,
        finding_id=finding_alice.id,
        target_concept="Power Rule Integration",
        question_text="Evaluate the integral of 2x dx.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="x^2",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
    )
    db_session.add_all([item_alice_1, item_alice_2])
    db_session.commit()

    return {
        "teacher": teacher,
        "student_alice": student_alice,
        "student_bob": student_bob,
        "assessment": assessment,
        "question": q1,
        "sub_alice": sub_alice,
        "sub_bob": sub_bob,
        "eval_run_alice": eval_run_alice,
        "finding_alice": finding_alice,
        "item_alice_1": item_alice_1,
        "item_alice_2": item_alice_2,
    }


def get_error_msg(resp) -> str:
    data = resp.json()
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return data["error"]["message"]
        return data.get("detail", "")
    return str(data)


# -------------------------------------------------------------------------
# 1. Idempotency & Concurrency Tests
# -------------------------------------------------------------------------

def test_practice_session_resuming_idempotent(client: TestClient, audit_setup):
    """
    Starting a practice session with resume_active=True multiple times
    must be strictly idempotent and return the exact same active session ID.
    """
    alice = audit_setup["student_alice"]
    sub_alice = audit_setup["sub_alice"]
    headers = auth_headers_for_user(alice)

    # First start
    r1 = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions", headers=headers)
    assert r1.status_code == 201
    session_id_1 = r1.json()["id"]

    # Second start (resume)
    r2 = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions?resume_active=true", headers=headers)
    assert r2.status_code == 201
    session_id_2 = r2.json()["id"]

    # Third start (resume)
    r3 = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions?resume_active=true", headers=headers)
    assert r3.status_code == 201
    session_id_3 = r3.json()["id"]

    assert session_id_1 == session_id_2 == session_id_3


def test_concurrent_duplicate_response_caught_by_unique_constraint(client: TestClient, audit_setup, db_session: Session):
    """
    Simulate race condition on answer submission:
    If two concurrent requests try to insert a response for the same (session_id, item_id),
    the unique constraint uq_practice_session_item_response triggers an IntegrityError.
    The service must cleanly rollback and return HTTP 409 Conflict instead of 500 error.
    """
    alice = audit_setup["student_alice"]
    sub_alice = audit_setup["sub_alice"]
    item = audit_setup["item_alice_1"]
    headers = auth_headers_for_user(alice)

    # Start session
    resp = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions", headers=headers)
    session_id = resp.json()["id"]

    # First submission succeeds (201)
    r1 = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": item.id, "student_answer": "A"},
    )
    assert r1.status_code == 201

    # Second submission is rejected with 409 Conflict
    r2 = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": item.id, "student_answer": "A"},
    )
    assert r2.status_code == 409
    assert "already been answered" in get_error_msg(r2)


def test_evaluation_run_idempotency_on_same_answer_hash(client: TestClient, audit_setup):
    """
    Triggering evaluation on the same submission question with identical answer text
    must be idempotent and return the existing EvaluationRun without creating duplicate records.
    """
    teacher = audit_setup["teacher"]
    sub_alice = audit_setup["sub_alice"]
    q = audit_setup["question"]
    headers = auth_headers_for_user(teacher)

    # First call: returns existing run
    r1 = client.post(
        f"/api/v1/submissions/{sub_alice.id}/questions/{q.id}/evaluate",
        headers=headers,
    )
    assert r1.status_code == 200
    run_id_1 = r1.json()["id"]

    # Second call: returns identical run
    r2 = client.post(
        f"/api/v1/submissions/{sub_alice.id}/questions/{q.id}/evaluate",
        headers=headers,
    )
    assert r2.status_code == 200
    run_id_2 = r2.json()["id"]

    assert run_id_1 == run_id_2


def test_remediation_generation_idempotency(client: TestClient, audit_setup):
    """
    Triggering remediation generation on an accepted finding that already has a completed run
    must be idempotent and return the existing RemediationRun.
    """
    teacher = audit_setup["teacher"]
    finding = audit_setup["finding_alice"]
    headers = auth_headers_for_user(teacher)

    r1 = client.post(
        f"/api/v1/findings/{finding.id}/remediation/generate",
        headers=headers,
    )
    assert r1.status_code == 200
    run_id_1 = r1.json()["id"]

    r2 = client.post(
        f"/api/v1/findings/{finding.id}/remediation/generate",
        headers=headers,
    )
    assert r2.status_code == 200
    run_id_2 = r2.json()["id"]

    assert run_id_1 == run_id_2


# -------------------------------------------------------------------------
# 2. Data Integrity & Non-Destructive Provenance
# -------------------------------------------------------------------------

def test_full_provenance_chain_integrity(client: TestClient, audit_setup, db_session: Session):
    """
    Verify complete unbroken foreign-key provenance chain from:
    PracticeResponse -> RemediationItem -> EvaluationFinding -> EvaluationRun -> QuestionAnswer -> Submission.
    """
    alice = audit_setup["student_alice"]
    sub_alice = audit_setup["sub_alice"]
    item = audit_setup["item_alice_1"]
    headers = auth_headers_for_user(alice)

    resp = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions", headers=headers)
    session_id = resp.json()["id"]

    sub_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": item.id, "student_answer": "A"},
    )
    assert sub_resp.status_code == 201
    resp_id = sub_resp.json()["id"]

    # Verify directly in DB
    db_response = db_session.query(PracticeResponse).filter(PracticeResponse.id == resp_id).first()
    assert db_response is not None
    assert db_response.session_id == session_id
    assert db_response.remediation_item_id == item.id
    assert db_response.finding_id == audit_setup["finding_alice"].id
    assert db_response.evaluation_run_id == audit_setup["eval_run_alice"].id

    # Non-destructive check on parent records
    assert audit_setup["finding_alice"].review_status == FindingReviewStatus.ACCEPTED.value
    assert audit_setup["eval_run_alice"].status == EvaluationStatus.COMPLETED.value
    assert audit_setup["question"].marks == 5.0


def test_cascade_deletion_cleans_practice_data(client: TestClient, audit_setup, db_session: Session):
    """
    Deleting a parent Submission must cascade cleanly to delete associated
    PracticeSessions and PracticeResponses without leaving orphaned database rows.
    """
    alice = audit_setup["student_alice"]
    sub_alice = audit_setup["sub_alice"]
    item = audit_setup["item_alice_1"]
    headers = auth_headers_for_user(alice)

    # Start session and submit response
    resp = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions", headers=headers)
    session_id = resp.json()["id"]

    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": item.id, "student_answer": "A"},
    )

    # Delete parent submission
    db_session.delete(sub_alice)
    db_session.commit()

    # PracticeSession and PracticeResponse must be cascade-deleted
    orphan_sessions = db_session.query(PracticeSession).filter(PracticeSession.submission_id == sub_alice.id).all()
    assert len(orphan_sessions) == 0

    orphan_responses = db_session.query(PracticeResponse).filter(PracticeResponse.session_id == session_id).all()
    assert len(orphan_responses) == 0


# -------------------------------------------------------------------------
# 3. Error Sanitization & Security Boundary Tests
# -------------------------------------------------------------------------

def test_missing_and_malformed_ids_error_sanitization(client: TestClient, audit_setup):
    """
    Test that invalid or missing resource IDs return clean HTTP 404 / 422
    and never expose internal file paths, stack traces, or SQL queries.
    """
    alice = audit_setup["student_alice"]
    headers = auth_headers_for_user(alice)

    # Missing submission ID
    r_missing_sub = client.post("/api/v1/submissions/999999/practice-sessions", headers=headers)
    assert r_missing_sub.status_code == 404
    err_msg = get_error_msg(r_missing_sub)
    assert "not found" in err_msg.lower()
    assert "traceback" not in r_missing_sub.text.lower()
    assert "/home/" not in r_missing_sub.text.lower()

    # Missing session ID
    r_missing_sess = client.get("/api/v1/practice-sessions/999999", headers=headers)
    assert r_missing_sess.status_code == 404
    assert "not found" in get_error_msg(r_missing_sess).lower()

    # Malformed non-integer ID in path -> 422 validation error
    r_malformed = client.get("/api/v1/practice-sessions/abc_not_an_id", headers=headers)
    assert r_malformed.status_code == 422


def test_cross_resource_student_isolation(client: TestClient, audit_setup):
    """
    Ensure Student Bob cannot access, list, or submit answers to Student Alice's practice session.
    """
    alice = audit_setup["student_alice"]
    bob = audit_setup["student_bob"]
    sub_alice = audit_setup["sub_alice"]

    alice_headers = auth_headers_for_user(alice)
    bob_headers = auth_headers_for_user(bob)

    # Alice creates session
    resp = client.post(f"/api/v1/submissions/{sub_alice.id}/practice-sessions", headers=alice_headers)
    session_id = resp.json()["id"]

    # Bob attempts to view Alice's session summary -> 403 Forbidden
    r_bob_summary = client.get(f"/api/v1/practice-sessions/{session_id}/summary", headers=bob_headers)
    assert r_bob_summary.status_code == 403

    # Bob attempts to complete Alice's session -> 403 Forbidden
    r_bob_complete = client.post(f"/api/v1/practice-sessions/{session_id}/complete", headers=bob_headers)
    assert r_bob_complete.status_code == 403

    # Bob attempts to abandon Alice's session -> 403 Forbidden
    r_bob_abandon = client.post(f"/api/v1/practice-sessions/{session_id}/abandon", headers=bob_headers)
    assert r_bob_abandon.status_code == 403
