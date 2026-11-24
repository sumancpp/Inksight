import hashlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    FindingCategory,
    FindingReviewAction,
    FindingReviewStatus,
    InvalidStateTransitionError,
    ProposalStatus,
    QuestionType,
    ReviewAction,
    SubmissionStatus,
    UploadStatus,
    UserRole,
    validate_finding_review_transition,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.models.matching import ProposedAnswer, TeacherReview
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User


@pytest.fixture
def eval_setup(client: TestClient, db_session: Session):
    """
    Sets up a complete evaluation test environment:
    - Teacher and Student users
    - LearningTopic
    - Assessment with two questions:
        - q1: has prompt, rubric, and expected_answer
        - q2: has prompt, but NO rubric and NO expected_answer
    - Submission with approved QuestionAnswer records
    """
    teacher = User(
        full_name="Prof. Evaluation",
        email="eval.teacher@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        full_name="Student Newton",
        email="student.newton@learngraph.edu",
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
        title="Differentiation Assessment",
        description="Testing power rule and product rule",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="State the derivative of f(x) = x^2 using the power rule.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        rubric="Must specify power rule d/dx(x^n) = n*x^(n-1) and result 2x.",
        expected_answer="f'(x) = 2x by the power rule.",
    )
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate the product function h(x) = f(x)*g(x).",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        rubric=None,  # Intentionally missing to test safety rule
        expected_answer=None,
    )
    q3 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Explain the product rule formula.",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
        rubric="Requires (fg)' = f'g + fg'.",
        expected_answer="(fg)' = f'g + fg'",
    )
    db_session.add_all([q1, q2, q3])
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
        original_filename="calc_test.pdf",
        stored_filename="calc_test_uuid.pdf",
        storage_path="/tmp/calc_test_uuid.pdf",
        content_type="application/pdf",
        file_size_bytes=2048,
        upload_status=UploadStatus.EXTRACTED.value,
    )
    db_session.add(upload)
    db_session.commit()

    extraction = OCRExtraction(
        upload_id=upload.id,
        provider_name="mock_ocr_provider",
        processing_status=UploadStatus.EXTRACTED.value,
        extracted_text="1. 2x\n2. (fg)' = f'g'",
        confidence=0.95,
        structured_segments=[
            {"segment_id": 1, "page": 1, "text": "1. 2x by power rule", "confidence": 0.95},
            {"segment_id": 2, "page": 1, "text": "2. (fg)' = f'*g' product rule", "confidence": 0.92},
        ],
    )
    db_session.add(extraction)
    db_session.commit()

    # qa1: teacher-approved answer
    qa1 = QuestionAnswer(
        submission_id=submission.id,
        question_id=q1.id,
        answer_text="f'(x) = 2x by the power rule",
    )
    # qa2: teacher-approved answer for question without rubric
    qa2 = QuestionAnswer(
        submission_id=submission.id,
        question_id=q2.id,
        answer_text="(fg)' = f'g + fg'",
    )
    # qa3: teacher-approved answer with a misconception
    qa3 = QuestionAnswer(
        submission_id=submission.id,
        question_id=q3.id,
        answer_text="(fg)' = f'*g' by product rule",
    )
    db_session.add_all([qa1, qa2, qa3])
    db_session.commit()

    # Create approved ProposedAnswer records linked to upload and extraction
    p1 = ProposedAnswer(
        submission_id=submission.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=q1.id,
        segment_id=1,
        proposed_text=qa1.answer_text,
        status=ProposalStatus.APPROVED.value,
    )
    p2 = ProposedAnswer(
        submission_id=submission.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=q2.id,
        segment_id=2,
        proposed_text=qa2.answer_text,
        status=ProposalStatus.APPROVED.value,
    )
    p3 = ProposedAnswer(
        submission_id=submission.id,
        upload_id=upload.id,
        ocr_extraction_id=extraction.id,
        question_id=q3.id,
        segment_id=3,
        proposed_text=qa3.answer_text,
        status=ProposalStatus.APPROVED.value,
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    # Record teacher approval audit records for qa1, qa2, qa3
    rev1 = TeacherReview(
        proposal_id=p1.id,
        submission_id=submission.id,
        question_id=q1.id,
        reviewer_id=teacher.id,
        action=ReviewAction.APPROVE.value,
        original_text=qa1.answer_text,
        final_text=qa1.answer_text,
    )
    rev2 = TeacherReview(
        proposal_id=p2.id,
        submission_id=submission.id,
        question_id=q2.id,
        reviewer_id=teacher.id,
        action=ReviewAction.APPROVE.value,
        original_text=qa2.answer_text,
        final_text=qa2.answer_text,
    )
    rev3 = TeacherReview(
        proposal_id=p3.id,
        submission_id=submission.id,
        question_id=q3.id,
        reviewer_id=teacher.id,
        action=ReviewAction.APPROVE.value,
        original_text=qa3.answer_text,
        final_text=qa3.answer_text,
    )
    db_session.add_all([rev1, rev2, rev3])
    db_session.commit()

    from tests.conftest import auth_headers_for_user
    client.headers.update(auth_headers_for_user(teacher))

    return {
        "teacher": teacher,
        "student": student,
        "topic": topic,
        "assessment": assessment,
        "questions": [q1, q2, q3],
        "submission": submission,
        "upload": upload,
        "extraction": extraction,
        "answers": [qa1, qa2, qa3],
        "proposals": [p1, p2, p3],
    }


def test_only_teacher_approved_answers_are_eligible(client: TestClient, db_session: Session, eval_setup):
    """
    Verifies that unreviewed proposed answers cannot be evaluated.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]

    # Delete teacher review records and approved proposals so answer is unreviewed
    db_session.query(TeacherReview).filter(TeacherReview.question_id == q1.id).delete()
    db_session.query(ProposedAnswer).filter(ProposedAnswer.question_id == q1.id).delete()
    db_session.commit()

    # Add an unreviewed proposal
    prop = ProposedAnswer(
        submission_id=submission.id,
        upload_id=eval_setup["upload"].id,
        ocr_extraction_id=eval_setup["extraction"].id,
        question_id=q1.id,
        proposed_text="Unreviewed OCR text",
        status=ProposalStatus.PROPOSED.value,
    )
    db_session.add(prop)
    db_session.commit()


    resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp.status_code == 422
    assert "unreviewed or unapproved" in resp.json()["error"]["message"].lower()


def test_missing_rubric_and_expected_answer_yields_insufficient_evidence(client: TestClient, eval_setup):
    """
    When question lacks both teacher-provided rubric and expected answer,
    evaluator safely returns 'insufficient_evidence' without fabricating standards.
    """
    submission = eval_setup["submission"]
    q2 = eval_setup["questions"][1]  # q2 has no rubric or expected answer

    resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q2.id}/evaluate")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "completed"
    findings = data["findings"]
    assert len(findings) == 1
    assert findings[0]["category"] == "insufficient_evidence"
    assert "lacks teacher-provided rubric" in findings[0]["rationale"].lower()
    assert findings[0]["evidence_excerpt"] is None
    assert 0.0 <= findings[0]["confidence"] <= 1.0


def test_empty_answer_yields_insufficient_evidence(client: TestClient, db_session: Session, eval_setup):
    """
    When the student answer is empty, evaluation safely returns 422 or insufficient evidence.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]
    qa1 = eval_setup["answers"][0]

    # Set answer_text to empty whitespace
    qa1.answer_text = "   "
    db_session.commit()

    resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp.status_code == 422
    assert "no answer text to evaluate" in resp.json()["error"]["message"].lower()


def test_deterministic_mock_findings_preserve_evidence_excerpt_and_rationale(client: TestClient, eval_setup):
    """
    Evaluates:
    1. Correct understanding finding with evidence excerpt.
    2. Misconception finding with concrete evidence excerpt from student text.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]
    q3 = eval_setup["questions"][2]

    # Evaluate Q1 (correct)
    resp1 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "completed"
    f1 = data1["findings"][0]
    assert f1["category"] == "correct_understanding"
    assert f1["evidence_excerpt"] is not None
    assert f1["evidence_excerpt"].lower() in "f'(x) = 2x by the power rule".lower()
    assert "accurately articulates" in f1["rationale"].lower()
    assert 0.0 <= f1["confidence"] <= 1.0

    # Evaluate Q3 (misconception: (fg)' = f'*g')
    resp3 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q3.id}/evaluate")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["status"] == "completed"
    f3 = data3["findings"][0]
    assert f3["category"] == "likely_misconception"
    assert f3["evidence_excerpt"] == "f'*g'"
    assert "confuses the product rule with the sum rule" in f3["rationale"].lower()
    assert 0.0 <= f3["confidence"] <= 1.0


def test_findings_trace_to_exact_answer_hash_and_provenance(client: TestClient, eval_setup):
    """
    Verifies that the evaluation run stores the exact SHA-256 hash and snapshot of evaluated answer.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]
    qa1 = eval_setup["answers"][0]

    expected_hash = hashlib.sha256(qa1.answer_text.strip().encode("utf-8")).hexdigest()

    resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp.status_code == 200
    data = resp.json()

    assert data["answer_text_hash"] == expected_hash
    assert data["answer_text_snapshot"] == qa1.answer_text
    assert data["question_answer_id"] == qa1.id
    assert data["evaluator_name"] == "mock_evaluator"


def test_duplicate_trigger_is_idempotent(client: TestClient, eval_setup):
    """
    Triggering evaluation twice on the same unchanged answer returns the existing run.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]

    resp1 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp1.status_code == 200
    run_id1 = resp1.json()["id"]

    resp2 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp2.status_code == 200
    run_id2 = resp2.json()["id"]

    assert run_id1 == run_id2


def test_reevaluation_after_teacher_correction_creates_distinct_version_run(client: TestClient, db_session: Session, eval_setup):
    """
    When a teacher corrects the student answer, the answer text hash changes,
    producing a new distinct EvaluationRun with its own snapshot.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]
    qa1 = eval_setup["answers"][0]

    # Initial evaluation
    resp1 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp1.status_code == 200
    run1 = resp1.json()

    # Teacher corrects the answer
    corrected_text = "f'(x) = 2x (Teacher correction: simplified notation)"
    qa1.answer_text = corrected_text
    db_session.commit()

    # Re-evaluate
    resp2 = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert resp2.status_code == 200
    run2 = resp2.json()

    assert run1["id"] != run2["id"]
    assert run1["answer_text_hash"] != run2["answer_text_hash"]
    assert run2["answer_text_snapshot"] == corrected_text

    # Verify query for question runs returns both runs ordered newest first
    list_resp = client.get(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluations")
    assert list_resp.status_code == 200
    runs_list = list_resp.json()
    assert len(runs_list) == 2
    assert runs_list[0]["id"] == run2["id"]
    assert runs_list[1]["id"] == run1["id"]


def test_evaluation_never_mutates_authoritative_answer_or_ocr(client: TestClient, db_session: Session, eval_setup):
    """
    Confirms evaluation runs are purely analytical and never mutate QuestionAnswer.answer_text,
    OCRExtraction, or ProposedAnswer.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]
    qa1 = eval_setup["answers"][0]
    upload = eval_setup["upload"]
    extraction = eval_setup["extraction"]

    original_answer_text = qa1.answer_text
    original_ocr_text = extraction.extracted_text

    client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")

    db_session.refresh(qa1)
    db_session.refresh(extraction)

    assert qa1.answer_text == original_answer_text
    assert extraction.extracted_text == original_ocr_text


def test_batch_submission_evaluation_endpoint(client: TestClient, eval_setup):
    """
    Tests POST /submissions/{id}/evaluate batch processing.
    """
    submission = eval_setup["submission"]

    resp = client.post(f"/api/v1/submissions/{submission.id}/evaluate")
    assert resp.status_code in (200, 202)
    if resp.status_code == 202:
        task_id = resp.json()["task_id"]
        status_resp = client.get(f"/api/v1/submissions/task-status/{task_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "SUCCESS"
        data = status_resp.json()["result"]
    else:
        data = resp.json()

    assert data["submission_id"] == submission.id
    assert data["total_runs"] == 3
    assert len(data["runs"]) == 3

    # Check GET /submissions/{id}/evaluations
    get_resp = client.get(f"/api/v1/submissions/{submission.id}/evaluations")
    assert get_resp.status_code == 200
    assert get_resp.json()["total_runs"] == 3


def test_teacher_finding_review_workflow_and_audit(client: TestClient, db_session: Session, eval_setup):
    """
    Teacher reviews a finding:
    - Accepts finding with review notes
    - Rejects finding with review notes
    - Checks audit history
    """
    submission = eval_setup["submission"]
    teacher = eval_setup["teacher"]
    student = eval_setup["student"]
    q3 = eval_setup["questions"][2]

    # Generate finding for Q3 (misconception)
    eval_resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q3.id}/evaluate")
    assert eval_resp.status_code == 200
    finding_id = eval_resp.json()["findings"][0]["id"]

    # 1. Non-teacher reviewer rejected
    from app.core.security import create_access_token
    from tests.conftest import auth_headers_for_user

    student_rev = client.post(
        f"/api/v1/evaluations/findings/{finding_id}/review",
        headers=auth_headers_for_user(student),
        json={
            "action": "accepted",
            "review_notes": "Student trying to review",
        },
    )
    assert student_rev.status_code in (403, 422)

    # 2. Non-existent reviewer rejected
    missing_token = create_access_token(subject="99999", role=UserRole.TEACHER.value)
    missing_rev = client.post(
        f"/api/v1/evaluations/findings/{finding_id}/review",
        headers={"Authorization": f"Bearer {missing_token}"},
        json={"action": "accepted"},
    )
    assert missing_rev.status_code in (401, 404)

    # 3. Teacher accepts finding
    teacher_rev = client.post(
        f"/api/v1/evaluations/findings/{finding_id}/review",
        json={
            "reviewer_id": teacher.id,
            "action": "accepted",
            "review_notes": "Confirmed student confused product rule with sum rule.",
        },
    )
    assert teacher_rev.status_code == 200
    rev_data = teacher_rev.json()

    assert rev_data["finding"]["review_status"] == "accepted"
    assert rev_data["finding"]["reviewed_by"] == teacher.id
    assert rev_data["finding"]["review_notes"] == "Confirmed student confused product rule with sum rule."
    assert rev_data["audit"]["action"] == "accepted"
    assert rev_data["audit"]["reviewer_id"] == teacher.id

    # 4. Teacher requests revision on accepted finding
    rev_again = client.post(
        f"/api/v1/evaluations/findings/{finding_id}/review",
        json={
            "reviewer_id": teacher.id,
            "action": "needs_revision",
            "review_notes": "Need to verify if student wrote this under time pressure.",
        },
    )
    assert rev_again.status_code == 200
    assert rev_again.json()["finding"]["review_status"] == "needs_revision"

    # 5. Invalid transition test directly on validator
    with pytest.raises(InvalidStateTransitionError):
        validate_finding_review_transition(FindingReviewStatus.REJECTED, FindingReviewStatus.ACCEPTED)

    with pytest.raises(InvalidStateTransitionError):
        validate_finding_review_transition(FindingReviewStatus.ACCEPTED, FindingReviewStatus.PENDING_REVIEW)


def test_get_evaluation_run_by_id(client: TestClient, eval_setup):
    """
    Tests GET /evaluations/runs/{run_id}.
    """
    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]

    eval_resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    run_id = eval_resp.json()["id"]

    get_resp = client.get(f"/api/v1/evaluations/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id
    assert get_resp.json()["submission_id"] == submission.id

    # Non-existent run -> 404
    missing_resp = client.get("/api/v1/evaluations/runs/999999")
    assert missing_resp.status_code == 404


def test_vllm_integration_and_honest_unavailable_state(client: TestClient, eval_setup, db_session, monkeypatch):
    """
    Verifies that when EVALUATOR_PROVIDER is 'vllm':
    1. If local VLLM is unreachable, evaluation returns HTTP 502 with actionable error.
    2. Does NOT silently fall back to mock output.
    3. /api/v1/providers explicitly reports vllm_reachable=False and offline status.
    4. When VLLM responds, findings are persisted with exact evidence grounding.
    """
    from unittest.mock import AsyncMock, MagicMock
    import json
    import httpx
    from app.core.config import settings

    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]

    # Set provider to vllm with fallback disabled for strict 502 test
    monkeypatch.setattr(settings, "EVALUATOR_PROVIDER", "vllm")
    monkeypatch.setattr(settings, "VLLM_BASE_URL", "http://127.0.0.1:9999/v1")  # unreachable port
    monkeypatch.setattr(settings, "ENABLE_EVALUATOR_FALLBACK", False)

    # 1. /api/v1/providers check
    prov_resp = client.get("/api/v1/providers")
    assert prov_resp.status_code == 200
    prov_data = prov_resp.json()
    assert prov_data["evaluator_provider"] == "vllm"
    assert prov_data["evaluator_real"] is True
    assert prov_data["vllm_reachable"] is False
    assert "unreachable" in prov_data["vllm_status_message"].lower()

    # 2. Evaluation fails honestly with 502 Bad Gateway
    eval_resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert eval_resp.status_code == 502
    err_body = eval_resp.json()
    err_msg = err_body.get("detail") or err_body.get("error", {}).get("message", "")
    assert "Cannot connect to local VLLM server" in err_msg

    # 3. Verify failed run was recorded as FAILED, never falling back to mock
    runs_resp = client.get(f"/api/v1/submissions/{submission.id}/evaluations")
    assert runs_resp.status_code == 200
    runs = runs_resp.json()["runs"]
    failed_run = [r for r in runs if r["question_id"] == q1.id][-1]
    assert failed_run["status"] == "failed"
    assert len(failed_run["findings"]) == 0
    assert "Cannot connect" in (failed_run["error_message"] or "")

    # 4. Now simulate online VLLM responding with valid findings
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "findings": [
                            {
                                "concept_name": "Power Rule",
                                "category": "correct_understanding",
                                "confidence": 0.95,
                                "evidence_excerpt": "d/dx(x^n) = n*x^(n-1)",
                                "rationale": "Correctly recalled power rule formula.",
                                "uncertainty_rationale": None,
                            }
                        ]
                    })
                }
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_post_resp

    # Monkeypatch VLLMEvaluator to use mock_client
    from app.services.evaluator.vllm_evaluator import VLLMEvaluator
    orig_init = VLLMEvaluator.__init__

    def patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self._external_client = mock_client

    monkeypatch.setattr(VLLMEvaluator, "__init__", patched_init)

    # Use distinct answer text to trigger new run
    from app.models.submission import QuestionAnswer
    qa = db_session.query(QuestionAnswer).filter(QuestionAnswer.question_id == q1.id).first()
    qa.answer_text = "I use d/dx(x^n) = n*x^(n-1) to solve."
    db_session.commit()

    success_resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert success_resp.status_code == 200
    success_data = success_resp.json()
    assert success_data["status"] == "completed"
    assert len(success_data["findings"]) == 1
    assert success_data["findings"][0]["concept_name"] == "Power Rule"
    assert success_data["findings"][0]["evidence_excerpt"] == "d/dx(x^n) = n*x^(n-1)"


def test_ai_health_and_graceful_fallback(client: TestClient, eval_setup, db_session, monkeypatch):
    """
    Verifies that:
    1. /api/v1/health/ai returns online/offline accurately without crashing.
    2. When VLLM is unreachable and ENABLE_EVALUATOR_FALLBACK is True, evaluation does NOT return 502,
       but gracefully falls back to mock evaluation annotating findings with the offline fallback message.
    """
    from app.core.config import settings
    from app.models.submission import QuestionAnswer

    submission = eval_setup["submission"]
    q1 = eval_setup["questions"][0]

    # Test /api/v1/health/ai when unreachable
    monkeypatch.setattr(settings, "EVALUATOR_PROVIDER", "vllm")
    monkeypatch.setattr(settings, "VLLM_BASE_URL", "http://127.0.0.1:9999/v1")
    monkeypatch.setattr(settings, "ENABLE_EVALUATOR_FALLBACK", True)

    health_resp = client.get("/api/v1/health/ai")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "offline"
    assert health_data["provider"] == "vllm"

    # Evaluation with fallback enabled
    qa = db_session.query(QuestionAnswer).filter(QuestionAnswer.question_id == q1.id).first()
    qa.answer_text = "I apply power rule: derivative of x^2 is 2x."
    db_session.commit()

    eval_resp = client.post(f"/api/v1/submissions/{submission.id}/questions/{q1.id}/evaluate")
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["status"] == "completed"
    assert len(eval_data["findings"]) > 0
    assert "AI is currently offline. Showing cached or mock evaluation." in eval_data["findings"][0]["uncertainty_rationale"]


