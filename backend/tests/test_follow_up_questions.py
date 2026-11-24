import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.conftest import auth_headers_for_user
from sqlalchemy.orm import Session

from app.models.enums import (
    FindingCategory,
    FindingReviewAction,
    FindingReviewStatus,
    FollowUpQuestionType,
    FollowUpStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.assessment import Assessment, Question
from app.models.submission import QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.evaluation import FindingReviewRequest
from app.schemas.follow_up import (
    FollowUpApproveRequest,
    FollowUpRejectRequest,
    FollowUpQuestionRead,
    Rubric,
    RubricCriterion,
)
from app.services.evaluation_service import evaluation_service
from app.services.followup_generation_service import followup_generation_service


@pytest.fixture
def setup_eval_context(db_session: Session):
    teacher = User(
        email="followup_teacher@example.com",
        full_name="Followup Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email="followup_student@example.com",
        full_name="Followup Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name="Calculus Differentiation", description="Derivatives")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Calculus Quiz", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Find the derivative of f(x) = x * sin(x)",
        expected_answer="sin(x) + x * cos(x)",
        rubric="Must apply product rule: f'g + fg'",
        question_type="short_answer",
        marks=2.0,
    )
    db_session.add(question)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=student.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=submission.id,
        question_id=question.id,
        answer_text="cos(x)",
    )
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=submission.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        status="completed",
        answer_text_hash="hash123",
        answer_text_snapshot="cos(x)",
    )
    db_session.add(run)
    db_session.commit()

    return {
        "teacher": teacher,
        "student": student,
        "topic": topic,
        "assessment": assessment,
        "question": question,
        "submission": submission,
        "run": run,
    }


@pytest.mark.anyio
async def test_followup_propose_refuses_unaccepted_finding(db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.88,
        rationale="Student omitted product rule",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.88, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "Product Rule Omission",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Product Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    # Guard check: status is pending_review, should refuse with 422
    with pytest.raises(HTTPException) as exc_info:
        await followup_generation_service.propose_follow_up(
            db=db_session,
            finding_id=finding.id,
            teacher_id=ctx["teacher"].id,
        )
    assert exc_info.value.status_code == 422
    assert "must be accepted by a teacher first" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_followup_propose_refuses_unacknowledged_low_confidence(db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.55,
        rationale="Uncertain finding",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=False,  # Teacher accepted without acknowledging uncertainty
        confidence_details={"score": 0.55, "level": "low", "uncertainty_reasons": ["unrecognized_structure"]},
        misconceptions=[
            {
                "hypothesis": "Product Rule Omission",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Product Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await followup_generation_service.propose_follow_up(
            db=db_session,
            finding_id=finding.id,
            teacher_id=ctx["teacher"].id,
        )
    assert exc_info.value.status_code == 422
    assert "acknowledged uncertainty" in exc_info.value.detail


@pytest.mark.anyio
async def test_followup_propose_refuses_no_misconceptions(db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.CORRECT_UNDERSTANDING.value,
        confidence=0.95,
        rationale="Fully correct answer",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.95, "level": "high", "uncertainty_reasons": []},
        misconceptions=[],
    )
    db_session.add(finding)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await followup_generation_service.propose_follow_up(
            db=db_session,
            finding_id=finding.id,
            teacher_id=ctx["teacher"].id,
        )
    assert exc_info.value.status_code == 422
    assert "no grounded misconception" in exc_info.value.detail


@pytest.mark.anyio
async def test_followup_propose_grounding_rejection(db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.90,
        rationale="Product rule confused",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.90, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "trigger_ungrounded_followup",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Product Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await followup_generation_service.propose_follow_up(
            db=db_session,
            finding_id=finding.id,
            teacher_id=ctx["teacher"].id,
        )
    assert exc_info.value.status_code == 422
    assert "grounding" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_followup_lifecycle_propose_approve_reject_and_list(db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.90,
        rationale="Product rule omission",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.90, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "Product Rule Omission",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Product Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    # 1. Propose follow-up
    proposed = await followup_generation_service.propose_follow_up(
        db=db_session,
        finding_id=finding.id,
        teacher_id=ctx["teacher"].id,
    )
    assert proposed.id is not None
    assert proposed.status == FollowUpStatus.PROPOSED.value
    assert proposed.proposed_by == "system"
    assert proposed.approved_by is None
    assert proposed.concept == "Product Rule"
    assert "Product Rule" in proposed.question_text
    assert proposed.rubric is not None
    rubric_model = Rubric.model_validate(proposed.rubric)
    assert sum(c.marks for c in rubric_model.criteria) > 0

    # 2. List follow-ups
    items = followup_generation_service.get_follow_ups_for_finding(db=db_session, finding_id=finding.id)
    assert len(items) == 1
    assert items[0].id == proposed.id

    # 3. Approve follow-up
    approved = followup_generation_service.approve_follow_up(
        db=db_session,
        follow_up_id=proposed.id,
        teacher_id=ctx["teacher"].id,
        audit_notes="Approved for student remediation quiz",
    )
    assert approved.status == FollowUpStatus.APPROVED.value
    assert approved.approved_by == ctx["teacher"].id
    assert approved.approved_at is not None
    assert "Approved for student remediation quiz" in approved.audit_notes

    # 4. Propose a second follow-up and reject it
    second = await followup_generation_service.propose_follow_up(
        db=db_session,
        finding_id=finding.id,
        teacher_id=ctx["teacher"].id,
    )
    assert second.status == FollowUpStatus.PROPOSED.value

    rejected = followup_generation_service.reject_follow_up(
        db=db_session,
        follow_up_id=second.id,
        teacher_id=ctx["teacher"].id,
        reason="Question too complex for this diagnostic checkpoint",
    )
    assert rejected.status == FollowUpStatus.REJECTED.value
    assert "Question too complex" in rejected.audit_notes

    # Verify total list now has 2
    items_after = followup_generation_service.get_follow_ups_for_finding(db=db_session, finding_id=finding.id)
    assert len(items_after) == 2


def test_followup_api_endpoints(client: TestClient, db_session: Session, setup_eval_context):
    ctx = setup_eval_context
    teacher_headers = auth_headers_for_user(ctx["teacher"])
    student_headers = auth_headers_for_user(ctx["student"])

    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.90,
        rationale="Product rule omission",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.90, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "Product Rule Omission",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Product Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    # 1. Propose follow-up via API
    propose_res = client.post(
        f"/api/v1/evaluations/findings/{finding.id}/follow-up/propose",
        headers=teacher_headers,
    )
    assert propose_res.status_code == 200, propose_res.text
    prop_data = propose_res.json()
    assert prop_data["status"] == "proposed"
    assert prop_data["concept"] == "Product Rule"
    follow_up_id = prop_data["id"]

    # Student cannot approve (RBAC check)
    student_app = client.post(
        f"/api/v1/evaluations/follow-ups/{follow_up_id}/approve",
        json={"audit_notes": "Student trying to approve"},
        headers=student_headers,
    )
    assert student_app.status_code == 403

    # Teacher approves
    approve_res = client.post(
        f"/api/v1/evaluations/follow-ups/{follow_up_id}/approve",
        json={"audit_notes": "Teacher verified question quality"},
        headers=teacher_headers,
    )
    assert approve_res.status_code == 200
    app_data = approve_res.json()
    assert app_data["status"] == "approved"
    assert app_data["approved_by"] == ctx["teacher"].id

    # List follow-ups
    list_res = client.get(
        f"/api/v1/evaluations/findings/{finding.id}/follow-ups",
        headers=student_headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == follow_up_id


@pytest.mark.anyio
async def test_followup_grounding_matches_linked_concept_when_not_in_hypothesis(db_session: Session, setup_eval_context):
    """Case 1: linked_concept is 'Chain Rule', but hypothesis does NOT contain 'Chain Rule'. Grounding must pass."""
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        rationale="Inner function derivative was completely skipped",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.92, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "Inner function derivative was completely skipped by student",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Chain Rule",
                "severity": "high",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    proposed = await followup_generation_service.propose_follow_up(
        db=db_session,
        finding_id=finding.id,
        teacher_id=ctx["teacher"].id,
    )
    assert proposed.id is not None
    assert proposed.concept == "Chain Rule"
    assert "Chain Rule" in proposed.question_text


@pytest.mark.anyio
async def test_followup_grounding_matches_hypothesis_when_not_in_linked_concept(db_session: Session, setup_eval_context):
    """Case 2: linked_concept is generic ('Calculus Method'), but hypothesis contains 'Quotient Rule'. Grounding must pass."""
    ctx = setup_eval_context
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        rationale="Denominator squaring omitted",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.92, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "trigger_hypothesis_grounding: Quotient Rule denominator squaring omitted",
                "evidence_excerpt": "cos(x)",
                "linked_concept": "Calculus Method",
                "severity": "medium",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    proposed = await followup_generation_service.propose_follow_up(
        db=db_session,
        finding_id=finding.id,
        teacher_id=ctx["teacher"].id,
    )
    assert proposed.id is not None
    assert proposed.concept == "Quotient Rule"
    assert "Quotient Rule" in proposed.question_text


def test_rubric_nested_validation():
    """
    GAP 4: Nested validation rules for Rubric and RubricCriterion:
    - RubricCriterion.text must have min_length=3
    - RubricCriterion.marks must be > 0 (accepts both int and float)
    - Rubric.criteria must have min_length=1
    """
    from pydantic import ValidationError
    from app.schemas.follow_up import Rubric, RubricCriterion

    # Valid rubric with int and float marks
    valid_rubric = Rubric(
        criteria=[
            RubricCriterion(text="Step 1: Inverts fraction divisor", marks=2),
            RubricCriterion(text="Step 2: Multiplies across numerators", marks=2.5),
        ]
    )
    assert len(valid_rubric.criteria) == 2
    assert valid_rubric.criteria[0].marks == 2
    assert valid_rubric.criteria[1].marks == 2.5

    # 0. Refactor confirmation: old dict-access no longer supported, must use .criteria attribute
    with pytest.raises(TypeError, match="not subscriptable"):
        _ = valid_rubric["criteria"]

    # 1. Rejects criterion text shorter than 3 characters
    with pytest.raises(ValidationError) as exc1:
        RubricCriterion(text="ab", marks=1)
    errors1 = exc1.value.errors()
    assert any("at least 3 characters" in e["msg"] or e["type"] == "string_too_short" for e in errors1)

    # 2. Rejects non-positive marks (marks <= 0)
    with pytest.raises(ValidationError) as exc2:
        RubricCriterion(text="Valid criterion text", marks=0)
    errors2 = exc2.value.errors()
    assert any("greater than 0" in e["msg"] or e["type"] == "greater_than" for e in errors2)

    with pytest.raises(ValidationError) as exc3:
        RubricCriterion(text="Valid criterion text", marks=-1.5)
    errors3 = exc3.value.errors()
    assert any("greater than 0" in e["msg"] or e["type"] == "greater_than" for e in errors3)

    # 3. Rejects empty criteria list (min_length=1)
    with pytest.raises(ValidationError) as exc4:
        Rubric(criteria=[])
    errors4 = exc4.value.errors()
    assert any("at least 1 item" in e["msg"] or e["type"] == "too_short" for e in errors4)
