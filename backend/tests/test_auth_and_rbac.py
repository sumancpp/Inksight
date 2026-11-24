import datetime
from datetime import timedelta
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.assessment import Assessment, Question
from app.models.enums import EvaluationStatus, FindingCategory, FindingReviewStatus, QuestionType, SubmissionStatus, UploadStatus, UserRole
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from tests.conftest import auth_headers_for_user


@pytest.fixture
def rbac_setup(db_session: Session):
    """
    Sets up a full multi-user, multi-role test fixture:
    - Teacher Alice (creator of Assessment 1)
    - Teacher Bob (unrelated teacher)
    - Student Charlie (owner of Submission 1)
    - Student David (another student)
    - Admin Eve
    - Inactive Frank
    """
    teacher_alice = User(
        full_name="Alice Teacher",
        email="alice@learngraph.edu",
        role=UserRole.TEACHER.value,
        hashed_password=hash_password("AlicePassword123!"),
        is_active=True,
    )
    teacher_bob = User(
        full_name="Bob Teacher",
        email="bob@learngraph.edu",
        role=UserRole.TEACHER.value,
        hashed_password=hash_password("BobPassword123!"),
        is_active=True,
    )
    student_charlie = User(
        full_name="Charlie Student",
        email="charlie@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("CharliePassword123!"),
        is_active=True,
    )
    student_david = User(
        full_name="David Student",
        email="david@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("DavidPassword123!"),
        is_active=True,
    )
    admin_eve = User(
        full_name="Eve Admin",
        email="eve@learngraph.edu",
        role=UserRole.ADMIN.value,
        hashed_password=hash_password("EvePassword123!"),
        is_active=True,
    )
    inactive_frank = User(
        full_name="Frank Inactive",
        email="frank@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("FrankPassword123!"),
        is_active=False,
    )
    db_session.add_all([teacher_alice, teacher_bob, student_charlie, student_david, admin_eve, inactive_frank])
    db_session.commit()

    topic = LearningTopic(
        name="Calculus Fundamentals",
        description="Limits and derivatives",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Calculus Quiz 1",
        description="Basic derivatives test",
        created_by=teacher_alice.id,
    )
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        question_type=QuestionType.ESSAY.value,
        prompt="Differentiate f(x) = x^3.",
        marks=5.0,
        expected_answer="f'(x) = 3x^2",
        rubric="Full marks for 3x^2.",
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student_charlie.id,
        status=SubmissionStatus.PROCESSING.value,
    )
    db_session.add(submission)
    db_session.commit()

    upload = AnswerSheetUpload(
        submission_id=submission.id,
        original_filename="charlie_scan.pdf",
        stored_filename="stored_charlie_scan.pdf",
        storage_path="/tmp/stored_charlie_scan.pdf",
        content_type="application/pdf",
        file_size_bytes=2048,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    return {
        "alice": teacher_alice,
        "bob": teacher_bob,
        "charlie": student_charlie,
        "david": student_david,
        "eve": admin_eve,
        "frank": inactive_frank,
        "topic": topic,
        "assessment": assessment,
        "question": question,
        "submission": submission,
        "upload": upload,
    }


def test_password_hashing_and_verification():
    """Verifies that bcrypt hashing produces non-reversible, salt-randomized hashes."""
    pwd = "SecurePassword123!"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)

    # Hashes are salted differently
    assert h1 != h2
    assert h1 != pwd

    # Verification works accurately
    assert verify_password(pwd, h1) is True
    assert verify_password(pwd, h2) is True
    assert verify_password("WrongPassword!", h1) is False


def test_user_registration(client: TestClient):
    """Verifies user registration endpoint and password encryption."""
    res = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "New Student",
            "email": "newstudent@learngraph.edu",
            "password": "StrongPassword999!",
            "role": "student",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "newstudent@learngraph.edu"
    assert data["role"] == "student"
    assert "password" not in data
    assert "hashed_password" not in data

    # Duplicate registration rejected
    res_dup = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Duplicate Student",
            "email": "newstudent@learngraph.edu",
            "password": "AnotherPassword999!",
            "role": "student",
        },
    )
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["error"]["message"]


def test_login_success_and_failure(client: TestClient, rbac_setup):
    """Verifies login credentials verification, JWT issuance, and rejection cases."""
    # 1. Valid credentials
    res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@learngraph.edu",
            "password": "AlicePassword123!",
        },
    )
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == "alice@learngraph.edu"
    assert token_data["user"]["role"] == "teacher"

    # 2. Invalid password
    res_bad_pwd = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@learngraph.edu",
            "password": "WrongPassword!",
        },
    )
    assert res_bad_pwd.status_code == 401
    assert "Incorrect email or password" in res_bad_pwd.json()["error"]["message"]

    # 3. Non-existent email
    res_no_user = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@learngraph.edu",
            "password": "AnyPassword!",
        },
    )
    assert res_no_user.status_code == 401
    assert "Incorrect email or password" in res_no_user.json()["error"]["message"]

    # 4. Inactive user login rejected
    res_inactive = client.post(
        "/api/v1/auth/login",
        json={
            "email": "frank@learngraph.edu",
            "password": "FrankPassword123!",
        },
    )
    assert res_inactive.status_code == 403
    assert "Inactive user account" in res_inactive.json()["error"]["message"]


def test_oauth2_token_form(client: TestClient, rbac_setup):
    """Verifies standard OAuth2 password request form flow (/auth/token)."""
    res = client.post(
        "/api/v1/auth/token",
        data={
            "username": "charlie@learngraph.edu",
            "password": "CharliePassword123!",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_auth_me_endpoint(client: TestClient, rbac_setup):
    """Verifies /auth/me returns identity for authenticated caller and rejects unauthenticated."""
    alice_headers = auth_headers_for_user(rbac_setup["alice"])

    # Valid token
    res = client.get("/api/v1/auth/me", headers=alice_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "alice@learngraph.edu"

    # Missing token
    res_unauth = client.get("/api/v1/auth/me")
    assert res_unauth.status_code == 401


def test_jwt_validation_invalid_and_expired(client: TestClient, rbac_setup):
    """Verifies that invalid, malformed, expired, or inactive tokens are rejected."""
    # 1. Malformed token
    res_malformed = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-token"})
    assert res_malformed.status_code == 401
    assert "Could not validate credentials" in res_malformed.json()["error"]["message"]

    # 2. Token signed with wrong secret
    bogus_token = jwt.encode(
        {"sub": str(rbac_setup["alice"].id), "exp": datetime.datetime.now(datetime.timezone.utc) + timedelta(minutes=15)},
        "completely-wrong-secret-key-1234567890",
        algorithm="HS256",
    )
    res_bogus = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bogus_token}"})
    assert res_bogus.status_code == 401

    # 3. Expired token
    expired_token = create_access_token(
        subject=str(rbac_setup["alice"].id),
        expires_delta=timedelta(seconds=-30),
    )
    res_expired = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["error"]["message"].lower()

    # 4. Inactive user token
    inactive_token = auth_headers_for_user(rbac_setup["frank"])
    res_inactive = client.get("/api/v1/auth/me", headers=inactive_token)
    assert res_inactive.status_code == 403
    assert "Inactive user account" in res_inactive.json()["error"]["message"]


def test_rbac_role_denial_student_attempting_teacher_routes(client: TestClient, rbac_setup):
    """Verifies that student callers cannot access teacher-only endpoints (403 Forbidden)."""
    charlie_headers = auth_headers_for_user(rbac_setup["charlie"])
    assessment_id = rbac_setup["assessment"].id
    submission_id = rbac_setup["submission"].id

    # POST /topics
    res1 = client.post(
        "/api/v1/topics",
        json={"name": "Illegal Topic", "description": "Attempted by student"},
        headers=charlie_headers,
    )
    assert res1.status_code == 403

    # POST /assessments
    res2 = client.post(
        "/api/v1/assessments",
        json={"title": "Illegal Assessment", "description": "Student exam"},
        headers=charlie_headers,
    )
    assert res2.status_code == 403

    # POST /assessments/{id}/questions
    res3 = client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={
            "topic_id": rbac_setup["topic"].id,
            "question_type": "short_answer",
            "prompt": "Illegal question",
            "marks": 5.0,
            "expected_answer": "ans",
            "rubric": "rubric",
        },
        headers=charlie_headers,
    )
    assert res3.status_code == 403

    # POST /submissions/{id}/match-answers
    res4 = client.post(
        f"/api/v1/submissions/{submission_id}/match-answers",
        headers=charlie_headers,
    )
    assert res4.status_code == 403

    # POST /proposed-answers/{id}/approve
    res5 = client.post(
        "/api/v1/proposed-answers/1/approve",
        json={"review_notes": "Student trying to approve"},
        headers=charlie_headers,
    )
    assert res5.status_code == 403

    # POST /submissions/{id}/questions/{id}/evaluate
    res6 = client.post(
        f"/api/v1/submissions/{submission_id}/questions/{rbac_setup['question'].id}/evaluate",
        headers=charlie_headers,
    )
    assert res6.status_code == 403

    # POST /evaluations/findings/{id}/review
    res7 = client.post(
        "/api/v1/evaluations/findings/1/review",
        json={"action": "accept", "review_notes": "Student trying to review finding"},
        headers=charlie_headers,
    )
    assert res7.status_code == 403

    # POST /findings/{id}/remediation/generate
    res8 = client.post(
        "/api/v1/findings/1/remediation/generate",
        headers=charlie_headers,
    )
    assert res8.status_code == 403

    # POST /remediations/items/{id}/review
    res9 = client.post(
        "/api/v1/remediations/items/1/review",
        json={"action": "approve", "review_notes": "Student trying to review item"},
        headers=charlie_headers,
    )
    assert res9.status_code == 403


def test_rbac_role_denial_teacher_attempting_student_submission(client: TestClient, rbac_setup):
    """Verifies that teachers cannot create student submissions."""
    alice_headers = auth_headers_for_user(rbac_setup["alice"])
    res = client.post(
        f"/api/v1/assessments/{rbac_setup['assessment'].id}/submissions",
        json={},
        headers=alice_headers,
    )
    assert res.status_code == 403
    assert "Operation not permitted" in res.json()["error"]["message"]


def test_ownership_denial_cross_student(client: TestClient, rbac_setup):
    """
    Verifies that Student David cannot access or manipulate Student Charlie's submission or uploads.
    """
    david_headers = auth_headers_for_user(rbac_setup["david"])
    charlie_headers = auth_headers_for_user(rbac_setup["charlie"])
    alice_headers = auth_headers_for_user(rbac_setup["alice"])
    submission_id = rbac_setup["submission"].id
    upload_id = rbac_setup["upload"].id

    # 1. David cannot view Charlie's submission (403)
    res_sub = client.get(f"/api/v1/submissions/{submission_id}", headers=david_headers)
    assert res_sub.status_code == 403

    # 2. David cannot view Charlie's submission answers (403)
    res_ans = client.get(f"/api/v1/submissions/{submission_id}/answers", headers=david_headers)
    assert res_ans.status_code == 403

    # 3. David cannot view Charlie's uploads (403)
    res_ups = client.get(f"/api/v1/submissions/{submission_id}/answer-sheets", headers=david_headers)
    assert res_ups.status_code == 403

    # 4. David cannot upload to Charlie's submission (403)
    res_up = client.post(
        f"/api/v1/submissions/{submission_id}/answer-sheets",
        files={"file": ("fake.pdf", b"%PDF-1.4...", "application/pdf")},
        headers=david_headers,
    )
    assert res_up.status_code == 403

    # 5. David cannot download Charlie's upload (403)
    res_dl = client.get(f"/api/v1/answer-sheets/{upload_id}/file", headers=david_headers)
    assert res_dl.status_code == 403

    # 6. David cannot trigger OCR for Charlie's upload (403)
    res_ocr = client.post(f"/api/v1/answer-sheets/{upload_id}/process", headers=david_headers)
    assert res_ocr.status_code == 403

    # 7. David cannot view Charlie's OCR extraction (403)
    res_ext = client.get(f"/api/v1/answer-sheets/{upload_id}/extraction", headers=david_headers)
    assert res_ext.status_code == 403

    # 8. David cannot view Charlie's evaluations (403)
    res_eval = client.get(
        f"/api/v1/submissions/{submission_id}/questions/{rbac_setup['question'].id}/evaluations",
        headers=david_headers,
    )
    assert res_eval.status_code == 403

    # 9. Charlie CAN view his own submission
    res_charlie = client.get(f"/api/v1/submissions/{submission_id}", headers=charlie_headers)
    assert res_charlie.status_code == 200
    assert res_charlie.json()["id"] == submission_id

    # 10. Teacher Alice CAN view Charlie's submission
    res_alice = client.get(f"/api/v1/submissions/{submission_id}", headers=alice_headers)
    assert res_alice.status_code == 200


def test_ownership_denial_cross_teacher_assessments(client: TestClient, rbac_setup):
    """
    Verifies that Teacher Bob cannot edit, add questions to, or delete Teacher Alice's assessment.
    Verifies that Admin Eve CAN modify/delete Teacher Alice's assessment.
    """
    bob_headers = auth_headers_for_user(rbac_setup["bob"])
    alice_headers = auth_headers_for_user(rbac_setup["alice"])
    eve_headers = auth_headers_for_user(rbac_setup["eve"])
    assessment_id = rbac_setup["assessment"].id

    # 1. Bob cannot update Alice's assessment (403)
    res_put = client.patch(
        f"/api/v1/assessments/{assessment_id}",
        json={"title": "Bob Hijacked Assessment"},
        headers=bob_headers,
    )
    assert res_put.status_code == 403
    assert "modify this assessment" in res_put.json()["error"]["message"]

    # 2. Bob cannot add questions to Alice's assessment (403)
    res_q = client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={
            "topic_id": rbac_setup["topic"].id,
            "question_type": "short_answer",
            "prompt": "Bob's question",
            "marks": 5.0,
            "expected_answer": "ans",
            "rubric": "rubric",
        },
        headers=bob_headers,
    )
    assert res_q.status_code == 403
    assert "add questions to this assessment" in res_q.json()["error"]["message"]

    # 3. Bob cannot delete Alice's assessment (403)
    res_del = client.delete(f"/api/v1/assessments/{assessment_id}", headers=bob_headers)
    assert res_del.status_code == 403
    assert "delete this assessment" in res_del.json()["error"]["message"]

    # 4. Alice CAN update her own assessment
    res_alice_put = client.patch(
        f"/api/v1/assessments/{assessment_id}",
        json={"title": "Alice Updated Title"},
        headers=alice_headers,
    )
    assert res_alice_put.status_code == 200
    assert res_alice_put.json()["title"] == "Alice Updated Title"

    # 5. Eve (Admin) CAN update Alice's assessment
    res_admin_put = client.patch(
        f"/api/v1/assessments/{assessment_id}",
        json={"title": "Admin Updated Title"},
        headers=eve_headers,
    )
    assert res_admin_put.status_code == 200
    assert res_admin_put.json()["title"] == "Admin Updated Title"


def test_spoofed_identity_fields_ignored_and_derived_from_token(client: TestClient, rbac_setup, db_session: Session):
    """
    Verifies that caller-supplied created_by, student_id, and reviewer_id are completely ignored,
    and identity is derived exclusively from the authenticated JWT token.
    """
    alice_headers = auth_headers_for_user(rbac_setup["alice"])
    charlie_headers = auth_headers_for_user(rbac_setup["charlie"])

    # 1. Assessment creation: spoofed created_by=99999 is ignored
    res_ass = client.post(
        "/api/v1/assessments",
        json={
            "title": "Token Identity Exam",
            "description": "Testing created_by derivation",
            "created_by": 99999,
        },
        headers=alice_headers,
    )
    assert res_ass.status_code == 201
    assert res_ass.json()["created_by"] == rbac_setup["alice"].id

    # 2. Submission creation for assessment with question: spoofed student_id=99999 is ignored
    res_sub = client.post(
        f"/api/v1/assessments/{rbac_setup['assessment'].id}/submissions",
        json={"student_id": 99999},
        headers=charlie_headers,
    )
    assert res_sub.status_code == 201
    assert res_sub.json()["student_id"] == rbac_setup["charlie"].id

    # 3. Matching and teacher review: spoofed reviewer_id=99999 is ignored
    sub_id = res_sub.json()["id"]
    # Add upload and OCR so matching can produce a proposal
    upload = AnswerSheetUpload(
        submission_id=sub_id,
        original_filename="scan.pdf",
        stored_filename="scan_uuid.pdf",
        storage_path="/tmp/scan_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    ocr = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr_provider",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="Question 1: f'(x) = 3x^2 is the derivative",
        confidence=0.9,
        structured_segments=[{"segment_id": 1, "page": 1, "text": "Question 1: f'(x) = 3x^2 is the derivative", "confidence": 0.9}],
    )
    db_session.add(ocr)
    db_session.commit()

    match_res = client.post(f"/api/v1/submissions/{sub_id}/match-answers", headers=alice_headers)
    assert match_res.status_code == 200
    proposal_id = match_res.json()["proposals"][0]["id"]

    res_app = client.post(
        f"/api/v1/proposed-answers/{proposal_id}/approve",
        json={"reviewer_id": 99999, "review_notes": "Token derived review"},
        headers=alice_headers,
    )
    assert res_app.status_code == 200
    assert res_app.json()["review"]["reviewer_id"] == rbac_setup["alice"].id


def test_teacher_answer_key_and_remediation_privacy(client: TestClient, rbac_setup, db_session: Session):
    """
    Verifies that remediation endpoints containing teacher_answer_key, teacher_rationale,
    and review notes are strictly protected behind teacher authorization, and cannot be accessed by students.
    """
    charlie_headers = auth_headers_for_user(rbac_setup["charlie"])
    alice_headers = auth_headers_for_user(rbac_setup["alice"])

    # Create dummy question answer, evaluation run, finding, remediation run, and remediation item
    qa = QuestionAnswer(
        submission_id=rbac_setup["submission"].id,
        question_id=rbac_setup["question"].id,
        answer_text="3x^2",
    )
    db_session.add(qa)
    db_session.commit()

    eval_run = EvaluationRun(
        submission_id=rbac_setup["submission"].id,
        question_id=rbac_setup["question"].id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="dummy_hash_12345",
        answer_text_snapshot="3x^2",
    )
    db_session.add(eval_run)
    db_session.commit()

    finding = EvaluationFinding(
        run_id=eval_run.id,
        topic_id=rbac_setup["topic"].id,
        concept_name="Power Rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.88,
        evidence_excerpt="3x^2",
        rationale="Detailed teacher rationale for error",
        review_status=FindingReviewStatus.ACCEPTED.value,
    )
    db_session.add(finding)
    db_session.commit()

    remed_run = RemediationRun(
        finding_id=finding.id,
        evaluation_run_id=eval_run.id,
        generator_name="mock_generator",
    )
    db_session.add(remed_run)
    db_session.commit()

    item = RemediationItem(
        run_id=remed_run.id,
        finding_id=finding.id,
        question_type="explain_reasoning",
        question_text="Why do we subtract 1 from the exponent?",
        teacher_answer_key="TOP_SECRET_ANSWER_KEY: Because d/dx(x^n) = n*x^(n-1)",
        teacher_rationale="TOP_SECRET_RATIONALE: Checks power rule fundamentals",
        target_concept="Power Rule",
        difficulty="easy",
    )
    db_session.add(item)
    db_session.commit()

    # 1. Unauthenticated requests are rejected (401)
    assert client.get(f"/api/v1/evaluations/runs/{eval_run.id}").status_code == 401
    assert client.get(f"/api/v1/remediations/runs/{remed_run.id}").status_code == 401
    assert client.get(f"/api/v1/findings/{finding.id}/remediations").status_code == 401
    assert client.post(f"/api/v1/findings/{finding.id}/remediation/generate").status_code == 401
    assert client.post(f"/api/v1/evaluations/findings/{finding.id}/review", json={"action": "accept"}).status_code == 401

    # 2. Student requests to remediation runs and finding remediations are rejected (403 Forbidden)
    res_student_run = client.get(f"/api/v1/remediations/runs/{remed_run.id}", headers=charlie_headers)
    assert res_student_run.status_code == 403

    res_student_remed = client.get(f"/api/v1/findings/{finding.id}/remediations", headers=charlie_headers)
    assert res_student_remed.status_code == 403

    # 3. Teacher requests succeed and include answer keys
    res_teacher_run = client.get(f"/api/v1/remediations/runs/{remed_run.id}", headers=alice_headers)
    assert res_teacher_run.status_code == 200
    items = res_teacher_run.json()["items"]
    assert len(items) == 1
    assert items[0]["teacher_answer_key"] == "TOP_SECRET_ANSWER_KEY: Because d/dx(x^n) = n*x^(n-1)"
    assert items[0]["teacher_rationale"] == "TOP_SECRET_RATIONALE: Checks power rule fundamentals"


def test_demo_session_endpoint(client: TestClient):
    """Verifies that the demo session endpoint safely issues valid bearer tokens for local demo use."""
    res = client.post("/api/v1/auth/demo-session")
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] in ["admin", "teacher"]
    assert data["user"]["email"] == "demo_admin@learngraph.edu"

    # Use the token to access a protected endpoint
    auth_headers = {"Authorization": f"Bearer {data['access_token']}"}
    me_res = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "demo_admin@learngraph.edu"

