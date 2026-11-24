import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    EvaluationStatus,
    FindingCategory,
    FindingReviewStatus,
    InvalidStateTransitionError,
    PracticeItemReviewAction,
    PracticeItemReviewStatus,
    PracticeQuestionType,
    ProposalStatus,
    QuestionType,
    RemediationRunStatus,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
    validate_practice_item_transition,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.remediation import RemediationItem, RemediationItemAudit, RemediationRun
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.remediation import RemediationItemStudentRead


@pytest.fixture
def remediation_setup(client: TestClient, db_session: Session):
    """
    Sets up a complete test environment for remediation generation:
    - Teacher and Student users
    - LearningTopic
    - Assessment with:
        - q1: Calculus product rule with prompt, rubric, and expected_answer
        - q2: Missing rubric and expected_answer
    - Submission, approved Answer, EvaluationRun
    - Multiple EvaluationFinding records:
        - finding_accepted: likely_misconception, accepted by teacher
        - finding_pending: likely_misconception, pending_review
        - finding_rejected: likely_misconception, rejected
        - finding_needs_revision: likely_misconception, needs_revision
        - finding_insufficient_ev: insufficient_evidence, accepted
        - finding_missing_context: likely_misconception, accepted, but on q2 (no rubric/expected answer)
    """
    teacher = User(
        full_name="Prof. Remediation",
        email="remed.teacher@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="Student Gauss",
        email="student.gauss@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(
        name="Calculus Differentiation",
        description="Core derivative concepts and calculus rules",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Differentiation Remediation Assessment",
        description="Testing product rule and power rule",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="State the product rule for differentiating f(x) * g(x).",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        rubric="Requires stating (fg)' = f'g + fg' with identification of terms.",
        expected_answer="(fg)' = f'g + fg'",
    )
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate the mystery function without rubric context.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        rubric=None,  # Missing rubric
        expected_answer=None,  # Missing expected answer
    )
    db_session.add_all([q1, q2])
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
        original_filename="remed_test.pdf",
        stored_filename="remed_test_uuid.pdf",
        storage_path="/tmp/remed_test_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=2048,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    qa1 = QuestionAnswer(
        submission_id=submission.id,
        question_id=q1.id,
        answer_text="(fg)' = f' * g' by product rule",
    )
    qa2 = QuestionAnswer(
        submission_id=submission.id,
        question_id=q2.id,
        answer_text="h'(x) = 2x",
    )
    db_session.add_all([qa1, qa2])
    db_session.commit()

    # Evaluation Runs
    eval_run1 = EvaluationRun(
        submission_id=submission.id,
        question_id=q1.id,
        question_answer_id=qa1.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_q1_mock_12345",
        answer_text_snapshot=qa1.answer_text,
    )
    eval_run2 = EvaluationRun(
        submission_id=submission.id,
        question_id=q2.id,
        question_answer_id=qa2.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_q2_mock_67890",
        answer_text_snapshot=qa2.answer_text,
    )
    db_session.add_all([eval_run1, eval_run2])
    db_session.commit()

    # Findings
    finding_accepted = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="product_rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        uncertainty_rationale="Explicitly equated product derivative to product of derivatives.",
        evidence_excerpt="f' * g'",
        rationale="Student confuses product rule with sum rule.",
        review_status=FindingReviewStatus.ACCEPTED.value,
        reviewed_by=teacher.id,
        review_notes="Confirmed diagnosis.",
    )
    finding_pending = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="product_rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        evidence_excerpt="f' * g'",
        rationale="Student confuses product rule with sum rule.",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
    )
    finding_rejected = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="product_rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        evidence_excerpt="f' * g'",
        rationale="Student confuses product rule with sum rule.",
        review_status=FindingReviewStatus.REJECTED.value,
        reviewed_by=teacher.id,
        review_notes="Rejected finding.",
    )
    finding_needs_revision = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="product_rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        evidence_excerpt="f' * g'",
        rationale="Student confuses product rule with sum rule.",
        review_status=FindingReviewStatus.NEEDS_REVISION.value,
        reviewed_by=teacher.id,
    )
    finding_insufficient_ev = EvaluationFinding(
        run_id=eval_run1.id,
        topic_id=topic.id,
        concept_name="product_rule",
        category=FindingCategory.INSUFFICIENT_EVIDENCE.value,
        confidence=0.0,
        rationale="Blank answer.",
        review_status=FindingReviewStatus.ACCEPTED.value,
        reviewed_by=teacher.id,
    )
    finding_missing_context = EvaluationFinding(
        run_id=eval_run2.id,
        topic_id=topic.id,
        concept_name="mystery_rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.8,
        evidence_excerpt="h'(x) = 2x",
        rationale="Some rationale on ungrounded question.",
        review_status=FindingReviewStatus.ACCEPTED.value,
        reviewed_by=teacher.id,
    )

    db_session.add_all([
        finding_accepted,
        finding_pending,
        finding_rejected,
        finding_needs_revision,
        finding_insufficient_ev,
        finding_missing_context,
    ])
    db_session.commit()

    from tests.conftest import auth_headers_for_user
    client.headers.update(auth_headers_for_user(teacher))

    return {
        "teacher": teacher,
        "student": student,
        "topic": topic,
        "assessment": assessment,
        "questions": [q1, q2],
        "submission": submission,
        "eval_runs": [eval_run1, eval_run2],
        "qa": [qa1, qa2],
        "finding_accepted": finding_accepted,
        "finding_pending": finding_pending,
        "finding_rejected": finding_rejected,
        "finding_needs_revision": finding_needs_revision,
        "finding_insufficient_ev": finding_insufficient_ev,
        "finding_missing_context": finding_missing_context,
    }


def test_only_accepted_findings_can_generate_practice(client: TestClient, remediation_setup):
    """
    Verifies that remediation generation strictly requires FindingReviewStatus.ACCEPTED.
    Pending, rejected, and needs_revision findings must be rejected with HTTP 422.
    """
    setup = remediation_setup

    # 1. Pending review finding -> 422
    resp_pending = client.post(
        f"/api/v1/findings/{setup['finding_pending'].id}/remediation/generate"
    )
    assert resp_pending.status_code == 422
    assert "teacher-accepted" in resp_pending.json()["error"]["message"].lower()

    # 2. Rejected finding -> 422
    resp_rejected = client.post(
        f"/api/v1/findings/{setup['finding_rejected'].id}/remediation/generate"
    )
    assert resp_rejected.status_code == 422
    assert "teacher-accepted" in resp_rejected.json()["error"]["message"].lower()

    # 3. Needs revision finding -> 422
    resp_rev = client.post(
        f"/api/v1/findings/{setup['finding_needs_revision'].id}/remediation/generate"
    )
    assert resp_rev.status_code == 422
    assert "teacher-accepted" in resp_rev.json()["error"]["message"].lower()

    # 4. Accepted finding -> 200 OK
    resp_accepted = client.post(
        f"/api/v1/findings/{setup['finding_accepted'].id}/remediation/generate"
    )
    assert resp_accepted.status_code == 200
    data = resp_accepted.json()
    assert data["status"] == "completed"
    assert len(data["items"]) > 0


def test_insufficient_evidence_finding_is_blocked(client: TestClient, remediation_setup):
    """
    Even if teacher-accepted, an insufficient_evidence finding must not generate remediation practice.
    """
    setup = remediation_setup
    resp = client.post(
        f"/api/v1/findings/{setup['finding_insufficient_ev'].id}/remediation/generate"
    )
    assert resp.status_code == 422
    assert "insufficient_evidence" in resp.json()["error"]["message"].lower()


def test_missing_question_context_returns_insufficient_context(client: TestClient, remediation_setup):
    """
    If the question lacks rubric and expected_answer, the generator returns status=insufficient_context
    without fabricating any practice items.
    """
    setup = remediation_setup
    resp = client.post(
        f"/api/v1/findings/{setup['finding_missing_context'].id}/remediation/generate"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_context"
    assert len(data["items"]) == 0
    assert "insufficient context" in data["error_message"].lower()


def test_deterministic_mock_generation_preserves_concept_and_separation(client: TestClient, remediation_setup):
    """
    Tests that mock generator produces deterministic practice items targeting the misconception:
    - Generates multiple choice and explain reasoning practice types
    - Separates student-facing prompt from teacher-only answer key and rationale
    - Does NOT leak the expected answer inside student question_text
    """
    setup = remediation_setup
    resp = client.post(
        f"/api/v1/findings/{setup['finding_accepted'].id}/remediation/generate"
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["generator_name"] == "mock_remediation_generator"
    assert len(data["items"]) == 2

    # Check first item (multiple choice)
    mc_item = data["items"][0]
    assert mc_item["question_type"] == "multiple_choice"
    assert mc_item["target_concept"] == "product_rule"
    assert mc_item["options"] is not None
    assert len(mc_item["options"]) == 4
    assert mc_item["teacher_answer_key"] is not None
    assert mc_item["teacher_rationale"] is not None
    assert "leibniz" in mc_item["teacher_rationale"].lower()
    # Confirm expected answer is NOT revealed in the question text
    assert "(fg)' = f'g + fg'" not in mc_item["question_text"]

    # Check second item (explain reasoning)
    er_item = data["items"][1]
    assert er_item["question_type"] == "explain_reasoning"
    assert er_item["target_concept"] == "product_rule"
    assert er_item["options"] is None
    assert er_item["teacher_answer_key"] is not None
    assert er_item["teacher_rationale"] is not None


def test_provenance_and_idempotent_duplicate_generation(client: TestClient, db_session: Session, remediation_setup):
    """
    Tests that:
    1. Generated items link directly to source finding and evaluation run.
    2. Re-triggering generation for the same finding is idempotent (returns existing run without duplicate rows).
    """
    setup = remediation_setup
    finding_id = setup["finding_accepted"].id

    # First trigger
    resp1 = client.post(f"/api/v1/findings/{finding_id}/remediation/generate")
    assert resp1.status_code == 200
    data1 = resp1.json()
    run_id1 = data1["id"]

    assert data1["finding_id"] == finding_id
    assert data1["evaluation_run_id"] == setup["eval_runs"][0].id

    # Second trigger (idempotent)
    resp2 = client.post(f"/api/v1/findings/{finding_id}/remediation/generate")
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data2["id"] == run_id1
    assert len(data2["items"]) == len(data1["items"])

    # Verify no duplicate runs or items in database
    runs_count = (
        db_session.query(RemediationRun)
        .filter(RemediationRun.finding_id == finding_id)
        .count()
    )
    assert runs_count == 1

    items_count = (
        db_session.query(RemediationItem)
        .filter(RemediationItem.finding_id == finding_id)
        .count()
    )
    assert items_count == len(data1["items"])


def test_generation_does_not_mutate_authoritative_or_evaluation_records(
    client: TestClient, db_session: Session, remediation_setup
):
    """
    Verifies the non-destructive invariant:
    Remediation generation never alters QuestionAnswer, Question, or EvaluationFinding records.
    """
    setup = remediation_setup
    qa_before = db_session.query(QuestionAnswer).filter(QuestionAnswer.id == setup["qa"][0].id).first().answer_text
    q_before = db_session.query(Question).filter(Question.id == setup["questions"][0].id).first().prompt
    finding_before_status = setup["finding_accepted"].review_status

    resp = client.post(f"/api/v1/findings/{setup['finding_accepted'].id}/remediation/generate")
    assert resp.status_code == 200

    qa_after = db_session.query(QuestionAnswer).filter(QuestionAnswer.id == setup["qa"][0].id).first().answer_text
    q_after = db_session.query(Question).filter(Question.id == setup["questions"][0].id).first().prompt
    finding_after = db_session.query(EvaluationFinding).filter(EvaluationFinding.id == setup["finding_accepted"].id).first()

    assert qa_after == qa_before
    assert q_after == q_before
    assert finding_after.review_status == finding_before_status


def test_teacher_practice_item_review_workflow_and_audit(client: TestClient, db_session: Session, remediation_setup):
    """
    Tests teacher review workflow on a generated practice item:
    - Non-teacher role rejected (422)
    - Missing reviewer rejected (404)
    - Teacher edits item (stores edited text separately and retains original)
    - Teacher approves edited item
    - Teacher rejects item
    - Audit history contains every action
    """
    setup = remediation_setup
    teacher = setup["teacher"]
    student = setup["student"]

    # Generate items
    resp = client.post(f"/api/v1/findings/{setup['finding_accepted'].id}/remediation/generate")
    item_id = resp.json()["items"][0]["id"]
    original_text = resp.json()["items"][0]["question_text"]

    # 1. Non-teacher reviewer rejected
    from app.core.security import create_access_token
    from tests.conftest import auth_headers_for_user

    student_rev = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        headers=auth_headers_for_user(student),
        json={
            "action": "approve",
        },
    )
    assert student_rev.status_code in (403, 422)

    # 2. Missing reviewer rejected
    missing_token = create_access_token(subject="99999", role=UserRole.TEACHER.value)
    missing_rev = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        headers={"Authorization": f"Bearer {missing_token}"},
        json={"action": "approve"},
    )
    assert missing_rev.status_code in (401, 404)

    # 3. Teacher edits item
    edit_resp = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        json={
            "reviewer_id": teacher.id,
            "action": "edit",
            "edited_question_text": "Custom prompt: Apply product rule to h(x) = sin(x) * cos(x).",
            "edited_answer_key": "h'(x) = cos^2(x) - sin^2(x)",
            "review_notes": "Tailored for trigonometric product rule practice.",
        },
    )
    assert edit_resp.status_code == 200
    edit_data = edit_resp.json()

    assert edit_data["item"]["review_status"] == "edited"
    assert edit_data["item"]["question_text"] == original_text  # Original text is preserved!
    assert edit_data["item"]["edited_question_text"] == "Custom prompt: Apply product rule to h(x) = sin(x) * cos(x)."
    assert edit_data["item"]["effective_question_text"] == "Custom prompt: Apply product rule to h(x) = sin(x) * cos(x)."
    assert edit_data["audit"]["action"] == "edit"
    assert edit_data["audit"]["new_status"] == "edited"

    # 4. Teacher approves edited item
    approve_resp = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        json={
            "reviewer_id": teacher.id,
            "action": "approve",
            "review_notes": "Approved tailored exercise.",
        },
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["item"]["review_status"] == "approved"

    # 5. Verify audit history in database
    audits = (
        db_session.query(RemediationItemAudit)
        .filter(RemediationItemAudit.item_id == item_id)
        .order_by(RemediationItemAudit.id.asc())
        .all()
    )
    assert len(audits) == 2
    assert audits[0].action == "edit"
    assert audits[1].action == "approve"


def test_invalid_state_transitions_on_practice_item(client: TestClient, remediation_setup):
    """
    Tests that invalid review transitions on practice items are rejected:
    e.g. A rejected item cannot transition directly to approved without being edited first.
    """
    setup = remediation_setup
    teacher = setup["teacher"]

    resp = client.post(f"/api/v1/findings/{setup['finding_accepted'].id}/remediation/generate")
    item_id = resp.json()["items"][0]["id"]

    # Reject item
    client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        json={"reviewer_id": teacher.id, "action": "reject"},
    )

    # Attempt direct approve from rejected -> rejected by validator (HTTP 422)
    invalid_approve = client.post(
        f"/api/v1/remediations/items/{item_id}/review",
        json={"reviewer_id": teacher.id, "action": "approve"},
    )
    assert invalid_approve.status_code == 422
    assert "invalid practice item state transition" in invalid_approve.json()["error"]["message"].lower()

    # Also verify transition validator unit logic
    with pytest.raises(InvalidStateTransitionError):
        validate_practice_item_transition(PracticeItemReviewStatus.REJECTED, PracticeItemReviewStatus.APPROVED)


def test_teacher_only_answer_key_not_exposed_in_student_schema(client: TestClient, remediation_setup):
    """
    Strict safety check:
    RemediationItemStudentRead must NEVER expose teacher_answer_key or teacher_rationale.
    """
    finding_id = remediation_setup["finding_accepted"].id
    resp = client.post(f"/api/v1/findings/{finding_id}/remediation/generate")
    item_dict = resp.json()["items"][0]

    student_view = RemediationItemStudentRead.model_validate(item_dict)
    student_dict = student_view.model_dump()

    assert "teacher_answer_key" not in student_dict
    assert "teacher_rationale" not in student_dict
    assert "review_notes" not in student_dict


def test_listing_and_retrieval_endpoints(client: TestClient, remediation_setup):
    """
    Tests:
    - GET /api/v1/findings/{id}/remediations
    - GET /api/v1/submissions/{id}/remediations
    - GET /api/v1/remediations/runs/{run_id}
    - GET /api/v1/remediations/items/{item_id}
    """
    setup = remediation_setup
    finding_id = setup["finding_accepted"].id
    submission_id = setup["submission"].id

    gen_resp = client.post(f"/api/v1/findings/{finding_id}/remediation/generate")
    run_id = gen_resp.json()["id"]
    item_id = gen_resp.json()["items"][0]["id"]

    # 1. By finding
    items_by_finding = client.get(f"/api/v1/findings/{finding_id}/remediations")
    assert items_by_finding.status_code == 200
    assert len(items_by_finding.json()) == 2

    # 2. By submission
    items_by_sub = client.get(f"/api/v1/submissions/{submission_id}/remediations")
    assert items_by_sub.status_code == 200
    assert len(items_by_sub.json()) == 2

    # 3. Run detail
    run_detail = client.get(f"/api/v1/remediations/runs/{run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["id"] == run_id
    assert len(run_detail.json()["items"]) == 2

    # 4. Item detail
    item_detail = client.get(f"/api/v1/remediations/items/{item_id}")
    assert item_detail.status_code == 200
    assert item_detail.json()["id"] == item_id

    # 5. Missing 404s
    assert client.get("/api/v1/remediations/runs/99999").status_code == 404
    assert client.get("/api/v1/remediations/items/99999").status_code == 404
    assert client.get("/api/v1/findings/99999/remediations").status_code == 404
    assert client.get("/api/v1/submissions/99999/remediations").status_code == 404
