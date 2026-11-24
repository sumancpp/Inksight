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
    PracticeSessionStatus,
    QuestionType,
    RemediationRunStatus,
    SubmissionStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.practice import PracticeResponse, PracticeSession
from app.models.remediation import RemediationItem, RemediationRun
from app.models.submission import QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from tests.conftest import auth_headers_for_user


def get_error_message(resp) -> str:
    data = resp.json()
    if isinstance(data, dict):
        if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
            return data["error"]["message"]
        return data.get("detail", "")
    return str(data)


@pytest.fixture
def practice_setup(db_session: Session):
    """
    Sets up a complete multi-user environment with:
    - Teacher Gauss
    - Student Alice (owner of Submission 1)
    - Student Bob (independent student)
    - LearningTopic, Assessment, Question
    - Submission 1 (Alice) & Submission 2 (Bob)
    - EvaluationRun & Accepted Finding for Submission 1
    - Multiple Remediation Items for Submission 1:
        - item_mcq_approved: Multiple choice, approved by teacher
        - item_short_approved: Short answer, approved by teacher with edited text and answer key
        - item_explain_approved: Explain reasoning, approved by teacher
        - item_pending: Pending review
        - item_rejected: Rejected by teacher
        - item_edited_unapproved: Edited by teacher, but not approved
    - EvaluationRun & Accepted Finding for Submission 2 (Bob) with 1 approved item
    """
    teacher = User(
        full_name="Prof. Gauss",
        email="gauss@learngraph.edu",
        role=UserRole.TEACHER.value,
        hashed_password=hash_password("ProfPassword123!"),
        is_active=True,
    )
    student_alice = User(
        full_name="Alice Student",
        email="alice.student@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("AlicePassword123!"),
        is_active=True,
    )
    student_bob = User(
        full_name="Bob Student",
        email="bob.student@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("BobPassword123!"),
        is_active=True,
    )
    db_session.add_all([teacher, student_alice, student_bob])
    db_session.commit()

    topic = LearningTopic(
        name="Calculus Differentiation",
        description="Core differential calculus topics",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Calculus Derivatives Quiz",
        description="Testing product and chain rules",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate f(x) = x^2 * sin(x).",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        expected_answer="f'(x) = 2x sin(x) + x^2 cos(x)",
    )
    db_session.add(q1)
    db_session.commit()

    sub1 = Submission(
        assessment_id=assessment.id,
        student_id=student_alice.id,
        status=SubmissionStatus.REVIEWED.value,
    )
    sub2 = Submission(
        assessment_id=assessment.id,
        student_id=student_bob.id,
        status=SubmissionStatus.REVIEWED.value,
    )
    db_session.add_all([sub1, sub2])
    db_session.commit()

    # Authoritative answer for Alice
    qa1 = QuestionAnswer(
        submission_id=sub1.id,
        question_id=q1.id,
        answer_text="2x cos(x)",
        awarded_marks=2.0,
    )
    # Authoritative answer for Bob
    qa2 = QuestionAnswer(
        submission_id=sub2.id,
        question_id=q1.id,
        answer_text="Bob initial answer",
        awarded_marks=1.0,
    )
    db_session.add_all([qa1, qa2])
    db_session.commit()

    # Evaluation Run and Finding for Alice
    eval_run1 = EvaluationRun(
        submission_id=sub1.id,
        question_id=q1.id,
        question_answer_id=qa1.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_alice_123",
        answer_text_snapshot=qa1.answer_text,
    )
    db_session.add(eval_run1)
    db_session.commit()

    finding1 = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="Product Rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        evidence_excerpt="2x cos(x)",
        rationale="Student multiplied derivatives instead of applying product rule formula.",
        review_status=FindingReviewStatus.ACCEPTED.value,
    )
    db_session.add(finding1)
    db_session.commit()

    # Remediation Run for Alice
    remed_run1 = RemediationRun(
        finding_id=finding1.id,
        evaluation_run_id=eval_run1.id,
        generator_name="mock_generator",
        status=RemediationRunStatus.COMPLETED.value,
    )
    db_session.add(remed_run1)
    db_session.commit()

    # Items for Alice
    # 1. Approved Multiple Choice
    item_mcq = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="What is the derivative of u(x) * v(x)?",
        question_type=PracticeQuestionType.MULTIPLE_CHOICE.value,
        options=["A) u'v + uv'", "B) u'v'", "C) uv + u'v'", "D) (uv)'"],
        teacher_answer_key="A",
        teacher_rationale="Standard Leibniz product rule definition",
        uncertainty_note="High confidence item",
        difficulty="easy",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
        review_notes="Approved for student delivery",
    )
    # 2. Approved Short Answer with Teacher Edits
    item_short = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="Original prompt: Compute derivative of x * e^x.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="e^x + x e^x",
        teacher_rationale="Apply product rule with u=x and v=e^x",
        uncertainty_note="None",
        difficulty="medium",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        edited_question_text="Teacher edited: Find the derivative of x * e^x.",
        edited_answer_key="e^x * (x + 1)",
        reviewed_by=teacher.id,
        review_notes="Updated prompt and factored answer key",
    )
    # 3. Approved Explain Reasoning
    item_explain = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="Explain why (u*v)' is not equal to u'*v' using the limit definition.",
        question_type=PracticeQuestionType.EXPLAIN_REASONING.value,
        teacher_answer_key="The limit of the product involves adding and subtracting intermediate terms.",
        teacher_rationale="Conceptual understanding of difference quotient expansion",
        difficulty="hard",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
    )
    # 4. Pending Review
    item_pending = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="Pending question: Compute derivative of x^3 * ln(x).",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="3x^2 ln(x) + x^2",
        review_status=PracticeItemReviewStatus.PENDING_REVIEW.value,
    )
    # 5. Rejected
    item_rejected = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="Rejected flawed prompt question.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="N/A",
        review_status=PracticeItemReviewStatus.REJECTED.value,
        reviewed_by=teacher.id,
        review_notes="Flawed prompt formulation",
    )
    # 6. Edited but NOT approved
    item_edited_unapproved = RemediationItem(
        run_id=remed_run1.id,
        finding_id=finding1.id,
        target_concept="Product Rule",
        question_text="Prompt edited but review pending.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="answer key",
        review_status=PracticeItemReviewStatus.EDITED.value,
        edited_question_text="Edited prompt awaiting final approval.",
        reviewed_by=teacher.id,
    )

    db_session.add_all([
        item_mcq, item_short, item_explain, item_pending, item_rejected, item_edited_unapproved
    ])
    db_session.commit()

    # Bob's Submission 2 setup with 1 approved item
    eval_run2 = EvaluationRun(
        submission_id=sub2.id,
        question_id=q1.id,
        question_answer_id=qa2.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_bob_123",
        answer_text_snapshot=qa2.answer_text,
    )
    db_session.add(eval_run2)
    db_session.commit()

    finding2 = EvaluationFinding(
        run_id=eval_run2.id,
        topic_id=topic.id,
        concept_name="Product Rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.85,
        evidence_excerpt="Bob finding excerpt",
        rationale="Bob's finding.",
        review_status=FindingReviewStatus.ACCEPTED.value,
    )
    db_session.add(finding2)
    db_session.commit()

    remed_run2 = RemediationRun(
        finding_id=finding2.id,
        evaluation_run_id=eval_run2.id,
        generator_name="mock_generator",
        status=RemediationRunStatus.COMPLETED.value,
    )
    db_session.add(remed_run2)
    db_session.commit()

    item_bob_approved = RemediationItem(
        run_id=remed_run2.id,
        finding_id=finding2.id,
        target_concept="Product Rule",
        question_text="Bob's approved practice item.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="Bob answer",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
    )
    db_session.add(item_bob_approved)
    db_session.commit()

    return {
        "teacher": teacher,
        "student_alice": student_alice,
        "student_bob": student_bob,
        "submission_alice": sub1,
        "submission_bob": sub2,
        "finding_alice": finding1,
        "item_mcq": item_mcq,
        "item_short": item_short,
        "item_explain": item_explain,
        "item_pending": item_pending,
        "item_rejected": item_rejected,
        "item_edited_unapproved": item_edited_unapproved,
        "item_bob_approved": item_bob_approved,
    }


def test_start_practice_session_approved_items_only(client: TestClient, practice_setup):
    """
    Test starting a practice session:
    - Only approved items are delivered (3 out of 6 for Alice).
    - Excludes pending_review, rejected, and edited-unapproved items.
    - Uses effective prompt (teacher edit if present).
    - Resuming returns the same active session.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    # Start session
    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()

    assert data["student_id"] == alice.id
    assert data["submission_id"] == sub_alice.id
    assert data["status"] == "active"
    assert data["total_items"] == 3
    assert data["completed_items"] == 0

    delivered_items = data["items"]
    assert len(delivered_items) == 3

    delivered_ids = {it["id"] for it in delivered_items}
    assert practice_setup["item_mcq"].id in delivered_ids
    assert practice_setup["item_short"].id in delivered_ids
    assert practice_setup["item_explain"].id in delivered_ids

    # Verify unapproved items are NOT in the delivered items
    assert practice_setup["item_pending"].id not in delivered_ids
    assert practice_setup["item_rejected"].id not in delivered_ids
    assert practice_setup["item_edited_unapproved"].id not in delivered_ids

    # Check effective prompt on item_short (teacher edited prompt took precedence)
    short_item = next(it for it in delivered_items if it["id"] == practice_setup["item_short"].id)
    assert short_item["question_text"] == "Teacher edited: Find the derivative of x * e^x."

    session_id = data["id"]

    # Starting again with resume_active=True returns the same session
    resume_resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions?resume_active=true",
        headers=headers,
    )
    assert resume_resp.status_code == 201
    assert resume_resp.json()["id"] == session_id


def test_student_data_privacy_before_submission(client: TestClient, practice_setup):
    """
    Test that delivered items strictly exclude confidential teacher data:
    - No teacher_answer_key
    - No teacher_rationale
    - No uncertainty_note
    - No review_notes / reviewer identity
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()

    # Check session details endpoint as well
    session_id = data["id"]
    detail_resp = client.get(
        f"/api/v1/practice-sessions/{session_id}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    items = detail_resp.json()["items"]

    forbidden_fields = [
        "teacher_answer_key",
        "teacher_rationale",
        "uncertainty_note",
        "review_notes",
        "reviewed_by",
        "edited_answer_key",
    ]

    for it in items:
        for field in forbidden_fields:
            assert field not in it, f"Field '{field}' was leaked in student item delivery!"


def test_submit_response_deterministic_scoring_and_provenance(client: TestClient, practice_setup, db_session: Session):
    """
    Test submitting student responses:
    - Deterministic grading on MCQ, Short Answer, and Explain Reasoning
    - Full provenance recorded (session_id, remediation_item_id, finding_id, evaluation_run_id)
    - Safe feedback returned without leaking teacher secrets
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    # Start session
    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]

    # 1. Submit correct answer for Multiple Choice (item_mcq)
    mcq_id = practice_setup["item_mcq"].id
    mcq_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": mcq_id, "student_answer": "A"},
    )
    assert mcq_resp.status_code == 201
    mcq_data = mcq_resp.json()
    assert mcq_data["is_correct"] is True
    assert mcq_data["score"] == 1.0
    assert "Correct!" in mcq_data["feedback"]
    assert mcq_data["finding_id"] == practice_setup["finding_alice"].id

    # 2. Submit correct answer for Short Answer (item_short) using effective edited key
    short_id = practice_setup["item_short"].id
    short_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": short_id, "student_answer": "e^x * (x + 1)"},
    )
    assert short_resp.status_code == 201
    short_data = short_resp.json()
    assert short_data["is_correct"] is True
    assert short_data["score"] == 1.0

    # 3. Submit incorrect answer for Explain Reasoning (item_explain)
    explain_id = practice_setup["item_explain"].id
    explain_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": explain_id, "student_answer": "i do not know"},
    )
    assert explain_resp.status_code == 201
    explain_data = explain_resp.json()
    assert explain_data["is_correct"] is False
    assert explain_data["score"] == 0.0
    assert "Needs revision" in explain_data["feedback"]

    # Verify response in database has complete provenance
    db_responses = db_session.query(PracticeResponse).filter(PracticeResponse.session_id == session_id).all()
    assert len(db_responses) == 3
    for r in db_responses:
        assert r.remediation_item_id is not None
        assert r.finding_id == practice_setup["finding_alice"].id
        assert r.evaluation_run_id is not None
        assert r.student_answer is not None


def test_data_privacy_after_submission(client: TestClient, practice_setup):
    """
    Test that after submitting an answer, returned response and session detail views
    strictly omit teacher_answer_key, teacher_rationale, and review_notes.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    # Start session
    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]
    mcq_id = practice_setup["item_mcq"].id

    submit_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": mcq_id, "student_answer": "B"},
    )
    assert submit_resp.status_code == 201
    submit_data = submit_resp.json()

    # Verify no teacher secrets in submit response
    forbidden = ["teacher_answer_key", "teacher_rationale", "review_notes", "uncertainty_note", "edited_answer_key"]
    for field in forbidden:
        assert field not in submit_data

    # Verify no teacher secrets in session detail responses list
    detail_resp = client.get(
        f"/api/v1/practice-sessions/{session_id}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    for r in detail_resp.json()["responses"]:
        for field in forbidden:
            assert field not in r


def test_prevent_duplicate_submission(client: TestClient, practice_setup):
    """
    Test that answering the same remediation item twice within a practice session
    is rejected with HTTP 409 Conflict.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]
    mcq_id = practice_setup["item_mcq"].id

    # First submission -> 201
    r1 = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": mcq_id, "student_answer": "A"},
    )
    assert r1.status_code == 201

    # Second submission for same item -> 409 Conflict
    r2 = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": mcq_id, "student_answer": "A"},
    )
    assert r2.status_code == 409
    assert "already been answered" in get_error_message(r2)


def test_prevent_cross_session_or_unapproved_item_submission(client: TestClient, practice_setup):
    """
    Test that:
    1. Submitting an item from Bob's submission to Alice's session returns 422.
    2. Submitting an unapproved item (e.g. pending or rejected) returns 422.
    3. Submitting a non-existent item returns 404.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]

    # 1. Foreign item from Bob
    bob_item_id = practice_setup["item_bob_approved"].id
    r_foreign = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": bob_item_id, "student_answer": "Bob answer"},
    )
    assert r_foreign.status_code == 422
    assert "does not belong to the submission" in get_error_message(r_foreign)

    # 2. Unapproved item (pending)
    pending_id = practice_setup["item_pending"].id
    r_unapproved = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": pending_id, "student_answer": "Some answer"},
    )
    assert r_unapproved.status_code == 422
    assert "not approved for student delivery" in get_error_message(r_unapproved)

    # 3. Non-existent item
    r_nonexistent = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": 999999, "student_answer": "Some answer"},
    )
    assert r_nonexistent.status_code == 404


def test_session_ownership_and_authorization(client: TestClient, practice_setup):
    """
    Test strict authorization and ownership boundaries:
    - Student Bob cannot view Alice's session (403 Forbidden).
    - Student Bob cannot list Alice's sessions (403 Forbidden).
    - Student Bob cannot submit answers to Alice's session (403 Forbidden).
    - Teacher cannot submit answers on behalf of a student (403 Forbidden).
    - Unauthenticated request returns 401 Unauthorized.
    """
    alice = practice_setup["student_alice"]
    bob = practice_setup["student_bob"]
    teacher = practice_setup["teacher"]
    sub_alice = practice_setup["submission_alice"]

    alice_headers = auth_headers_for_user(alice)
    bob_headers = auth_headers_for_user(bob)
    teacher_headers = auth_headers_for_user(teacher)

    # Alice creates session
    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=alice_headers,
    )
    assert resp.status_code == 201
    session_id = resp.json()["id"]

    # 1. Bob tries to view Alice's session -> 403
    r_bob_view = client.get(
        f"/api/v1/practice-sessions/{session_id}",
        headers=bob_headers,
    )
    assert r_bob_view.status_code == 403
    assert "Not authorized" in get_error_message(r_bob_view)

    # 2. Bob tries to list Alice's sessions -> 403
    r_bob_list = client.get(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=bob_headers,
    )
    assert r_bob_list.status_code == 403

    # 3. Bob tries to submit response to Alice's session -> 403
    r_bob_submit = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=bob_headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    assert r_bob_submit.status_code == 403

    # 4. Teacher tries to submit answer to Alice's practice session -> 403
    r_teacher_submit = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=teacher_headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    assert r_teacher_submit.status_code == 403

    # 5. Unauthenticated request -> 401
    r_unauth = client.get(f"/api/v1/practice-sessions/{session_id}")
    assert r_unauth.status_code == 401


def test_session_state_transitions(client: TestClient, practice_setup):
    """
    Test explicit practice session state transitions:
    - Active -> Completed (valid)
    - Submitting answer to Completed session -> 422
    - Completed -> Abandoned (invalid -> 422)
    - Completed -> Completed (invalid -> 422)
    - Active -> Abandoned (valid)
    - Submitting answer to Abandoned session -> 422
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    # 1. Create session (starts active)
    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]
    assert resp.json()["status"] == "active"

    # 2. Complete session
    complete_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/complete",
        headers=headers,
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "completed"

    # 3. Attempt to submit answer to completed session -> 422
    submit_resp = client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    assert submit_resp.status_code == 422
    assert "Cannot submit answers to a practice session that is 'completed'" in get_error_message(submit_resp)

    # 4. Attempt to complete already completed session -> 422
    again_complete = client.post(
        f"/api/v1/practice-sessions/{session_id}/complete",
        headers=headers,
    )
    assert again_complete.status_code == 422

    # 5. Attempt to abandon completed session -> 422
    abandon_completed = client.post(
        f"/api/v1/practice-sessions/{session_id}/abandon",
        headers=headers,
    )
    assert abandon_completed.status_code == 422

    # 6. Test abandoning an active session:
    # First, start new session by passing resume_active=false
    new_resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions?resume_active=false",
        headers=headers,
    )
    new_session_id = new_resp.json()["id"]

    abandon_resp = client.post(
        f"/api/v1/practice-sessions/{new_session_id}/abandon",
        headers=headers,
    )
    assert abandon_resp.status_code == 200
    assert abandon_resp.json()["status"] == "abandoned"

    # Submitting to abandoned session -> 422
    submit_abandoned = client.post(
        f"/api/v1/practice-sessions/{new_session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    assert submit_abandoned.status_code == 422


def test_session_auto_completion_on_all_answered(client: TestClient, practice_setup):
    """
    Test that when all deliverable practice items are answered,
    the session automatically updates completed_items and transitions status to 'completed'.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]
    assert resp.json()["total_items"] == 3

    # Answer item 1
    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    s1 = client.get(f"/api/v1/practice-sessions/{session_id}", headers=headers).json()
    assert s1["completed_items"] == 1
    assert s1["status"] == "active"

    # Answer item 2
    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_short"].id, "student_answer": "e^x * (x + 1)"},
    )
    s2 = client.get(f"/api/v1/practice-sessions/{session_id}", headers=headers).json()
    assert s2["completed_items"] == 2
    assert s2["status"] == "active"

    # Answer item 3 (final item)
    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_explain"].id, "student_answer": "The limit expands into cross terms and intermediate terms."},
    )
    s3 = client.get(f"/api/v1/practice-sessions/{session_id}", headers=headers).json()
    assert s3["completed_items"] == 3
    assert s3["status"] == "completed"
    assert s3["completed_at"] is not None


def test_session_formative_summary_and_disclaimer(client: TestClient, practice_setup):
    """
    Test compiling practice session formative evaluation summary:
    - Accurate counts, scores, and accuracy percentages.
    - Concept-level progress breakdown.
    - Explicit pedagogical disclaimer stating evidence is formative practice and avoiding unsupported mastery claims.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]

    # Submit 1 correct and 1 incorrect
    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_mcq"].id, "student_answer": "A"},
    )
    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": practice_setup["item_short"].id, "student_answer": "wrong answer"},
    )

    summary_resp = client.get(
        f"/api/v1/practice-sessions/{session_id}/summary",
        headers=headers,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert summary["session_id"] == session_id
    assert summary["total_items"] == 3
    assert summary["completed_items"] == 2
    assert summary["correct_count"] == 1
    assert summary["total_score"] == 1.0
    assert summary["max_score"] == 3.0
    assert summary["accuracy_percentage"] == 33.33

    assert len(summary["concepts_practiced"]) >= 1
    concept_stat = summary["concepts_practiced"][0]
    assert concept_stat["concept_name"] == "Product Rule"
    assert concept_stat["items_count"] == 2
    assert concept_stat["correct_count"] == 1

    # Verify transparent disclaimer
    assert "pedagogical_disclaimer" in summary
    assert "formative exercise evidence" in summary["pedagogical_disclaimer"].lower()
    assert "not certified concept mastery" in summary["pedagogical_disclaimer"].lower()


def test_no_approved_items_returns_422(client: TestClient, db_session: Session):
    """
    Test that attempting to start a practice session for a submission
    without any teacher-approved remediation items returns 422 Unprocessable Entity.
    """
    student = User(
        full_name="New Student",
        email="new.student@learngraph.edu",
        role=UserRole.STUDENT.value,
        hashed_password=hash_password("Pass123!"),
        is_active=True,
    )
    db_session.add(student)
    db_session.commit()

    assessment = Assessment(title="Empty Assessment", created_by=student.id)
    db_session.add(assessment)
    db_session.commit()

    sub = Submission(assessment_id=assessment.id, student_id=student.id)
    db_session.add(sub)
    db_session.commit()

    headers = auth_headers_for_user(student)
    resp = client.post(
        f"/api/v1/submissions/{sub.id}/practice-sessions",
        headers=headers,
    )
    assert resp.status_code == 422
    assert "No teacher-approved practice items are currently available" in get_error_message(resp)


def test_non_destructive_practice_session(client: TestClient, practice_setup, db_session: Session):
    """
    Test non-destructive behavior:
    Starting practice sessions and answering questions must never mutate
    or overwrite original RemediationItem, EvaluationFinding, or EvaluationRun records.
    """
    alice = practice_setup["student_alice"]
    sub_alice = practice_setup["submission_alice"]
    headers = auth_headers_for_user(alice)

    orig_item = practice_setup["item_mcq"]
    orig_text = orig_item.question_text
    orig_key = orig_item.teacher_answer_key
    orig_status = orig_item.review_status

    resp = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=headers,
    )
    session_id = resp.json()["id"]

    client.post(
        f"/api/v1/practice-sessions/{session_id}/responses",
        headers=headers,
        json={"remediation_item_id": orig_item.id, "student_answer": "A"},
    )

    db_session.expire_all()
    reloaded_item = db_session.query(RemediationItem).filter(RemediationItem.id == orig_item.id).first()
    assert reloaded_item.question_text == orig_text
    assert reloaded_item.teacher_answer_key == orig_key
    assert reloaded_item.review_status == orig_status
