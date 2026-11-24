import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import (
    CorrectionFieldName,
    CorrectionStatus,
    FindingCategory,
    FindingReviewAction,
    FindingReviewStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun, FindingReviewAudit
from app.models.correction import FindingCorrection
from app.models.assessment import Assessment, Question
from app.models.submission import QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.evaluation import FindingReviewRequest
from app.schemas.correction import FindingCorrectionCreate
from app.services.correction_service import correction_service, resolve_finding_field
from app.services.followup_generation_service import followup_generation_service
from app.services.remediation_service import remediation_service
from tests.conftest import auth_headers_for_user


@pytest.fixture
def correction_env(db_session: Session):
    teacher = User(
        email="correction_teacher@example.com",
        full_name="Correction Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    student = User(
        email="correction_student@example.com",
        full_name="Correction Student",
        hashed_password="pw",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, student])
    db_session.commit()

    topic = LearningTopic(name="Differentiation Rules", description="Calculus")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Calculus Exam", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate f(x) = (3x + 1)^4",
        expected_answer="12(3x + 1)^3",
        rubric="Must apply chain rule",
        question_type="short_answer",
        marks=3.0,
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
        answer_text="4(3x + 1)^3",
    )
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=submission.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        status="completed",
        answer_text_hash="hash999",
        answer_text_snapshot="4(3x + 1)^3",
    )
    db_session.add(run)
    db_session.commit()

    finding = EvaluationFinding(
        run_id=run.id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.50,
        evidence_excerpt="4(3x + 1)^3",
        rationale="Student omitted inner derivative",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=True,
        confidence_details={"score": 0.50, "level": "low", "uncertainty_reasons": ["unrecognized_structure"]},
        misconceptions=[
            {
                "hypothesis": "Omitted inner derivative multiplier",
                "evidence_excerpt": "4(3x + 1)^3",
                "linked_concept": "Chain Rule",
                "severity": "medium",
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()

    return {
        "teacher": teacher,
        "student": student,
        "topic": topic,
        "assessment": assessment,
        "question": question,
        "submission": submission,
        "run": run,
        "finding": finding,
    }


def test_apply_correction_persists_reason_and_audit(db_session: Session, correction_env):
    ctx = correction_env
    finding = ctx["finding"]

    # 1. Apply correction to linked_concept
    corr = correction_service.apply_correction(
        db=db_session,
        finding_id=finding.id,
        field_name=CorrectionFieldName.LINKED_CONCEPT,
        new_value="Composite Function Power Rule",
        reason="More accurate pedagogical label for this specific error",
        teacher_id=ctx["teacher"].id,
    )
    assert corr.id is not None
    assert corr.status == CorrectionStatus.ACTIVE.value
    assert corr.original_value == "Chain Rule"
    assert corr.corrected_value == "Composite Function Power Rule"
    assert corr.correction_reason == "More accurate pedagogical label for this specific error"
    assert corr.corrected_by == ctx["teacher"].id

    # Verify audit logged
    audit = (
        db_session.query(FindingReviewAudit)
        .filter(FindingReviewAudit.finding_id == finding.id, FindingReviewAudit.action == "corrected")
        .order_by(FindingReviewAudit.id.desc())
        .first()
    )
    assert audit is not None
    assert "Composite Function Power Rule" in audit.review_notes

    # Verify finding.teacher_corrected is True
    db_session.refresh(finding)
    assert finding.teacher_corrected is True


def test_revert_to_ai_restores_original_value(db_session: Session, correction_env):
    ctx = correction_env
    finding = ctx["finding"]

    corr = correction_service.apply_correction(
        db=db_session,
        finding_id=finding.id,
        field_name=CorrectionFieldName.EVIDENCE_EXCERPT,
        new_value="4(3x+1)^3 without inner factor 3",
        reason="Clarified student expression",
        teacher_id=ctx["teacher"].id,
    )
    assert corr.status == CorrectionStatus.ACTIVE.value

    # Now revert
    rev = correction_service.revert_to_ai(
        db=db_session,
        finding_id=finding.id,
        correction_id=corr.id,
        teacher_id=ctx["teacher"].id,
    )
    assert rev.status == CorrectionStatus.REVERTED.value

    # Field on finding should be back to original
    db_session.refresh(finding)
    assert finding.evidence_excerpt == "4(3x + 1)^3"

    # Audit logged for revert
    rev_audit = (
        db_session.query(FindingReviewAudit)
        .filter(FindingReviewAudit.finding_id == finding.id, FindingReviewAudit.action == "reverted_correction")
        .first()
    )
    assert rev_audit is not None
    assert "Reverted evidence_excerpt" in rev_audit.review_notes


@pytest.mark.anyio
async def test_transitive_downstream_read_rule_note_a(db_session: Session, correction_env):
    """Note A: When downstream services read misconception fields, resolver MUST return active correction."""
    ctx = correction_env
    finding = ctx["finding"]

    # Initial state: linked_concept is "Chain Rule"
    assert resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT) == "Chain Rule"

    # Teacher corrects to "Product Rule"
    correction_service.apply_correction(
        db=db_session,
        finding_id=finding.id,
        field_name=CorrectionFieldName.LINKED_CONCEPT,
        new_value="Product Rule",
        reason="Correction to test transitive resolver",
        teacher_id=ctx["teacher"].id,
    )

    db_session.refresh(finding)
    # Direct resolver check
    assert resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT) == "Product Rule"
    assert resolve_finding_field(finding, CorrectionFieldName.LINKED_CONCEPT) != "Chain Rule"

    # Downstream Consumer 1: Follow-up generation service
    # Follow-up generation should use "Product Rule", not "Chain Rule"
    follow_up = await followup_generation_service.propose_follow_up(
        db=db_session,
        finding_id=finding.id,
        teacher_id=ctx["teacher"].id,
    )
    assert follow_up.concept == "Product Rule"
    assert "Product Rule" in follow_up.question_text

    # Downstream Consumer 2: Remediation Practice service
    # When generating practice items, RemediationInput receives resolved concept
    remediation_res = await remediation_service.generate_remediation_for_finding(
        db=db_session,
        finding_id=finding.id,
        generator_name="mock",
    )
    assert remediation_res.status == "completed"
    items = remediation_service.get_items_by_finding(db=db_session, finding_id=finding.id)
    assert len(items) > 0


def test_confidence_correction_edge_case_note_b(db_session: Session, correction_env):
    """Note B: When confidence_score is corrected low->high, requires_teacher_review does NOT auto-clear.
    It stays True until teacher explicitly re-reviews."""
    ctx = correction_env
    finding = ctx["finding"]

    # Finding begins with score=0.50, level='low', requires_teacher_review=True
    assert finding.confidence == 0.50
    assert finding.requires_teacher_review is True

    # Teacher corrects confidence to 0.95 (high confidence)
    corr = correction_service.apply_correction(
        db=db_session,
        finding_id=finding.id,
        field_name=CorrectionFieldName.CONFIDENCE_SCORE,
        new_value=0.95,
        reason="Teacher confirmed answer is unquestionably high confidence upon manual review",
        teacher_id=ctx["teacher"].id,
    )
    db_session.refresh(finding)

    assert finding.confidence == 0.95
    assert finding.confidence_details["score"] == 0.95
    assert finding.confidence_details["level"] == "high"

    # CRITICAL: requires_teacher_review MUST STAY True!
    assert finding.requires_teacher_review is True


def test_corrections_api_flow(client: TestClient, db_session: Session, correction_env):
    ctx = correction_env
    finding = ctx["finding"]
    teacher_headers = auth_headers_for_user(ctx["teacher"])
    student_headers = auth_headers_for_user(ctx["student"])

    # 1. Student forbidden from applying correction
    student_post = client.post(
        f"/api/v1/evaluations/findings/{finding.id}/corrections",
        json={
            "field_name": "misconception_hypothesis",
            "corrected_value": "Student hypothesis",
            "correction_reason": "Student attempt",
        },
        headers=student_headers,
    )
    assert student_post.status_code == 403

    # 2. Validation: empty reason rejected with 422
    empty_reason = client.post(
        f"/api/v1/evaluations/findings/{finding.id}/corrections",
        json={
            "field_name": "misconception_hypothesis",
            "corrected_value": "New hypothesis",
            "correction_reason": "   ",
        },
        headers=teacher_headers,
    )
    assert empty_reason.status_code == 422

    # 3. Teacher creates correction
    create_res = client.post(
        f"/api/v1/evaluations/findings/{finding.id}/corrections",
        json={
            "field_name": "misconception_hypothesis",
            "corrected_value": "Omitted factor of 3 from derivative of inner term",
            "correction_reason": "Specific precision added for clarification",
        },
        headers=teacher_headers,
    )
    assert create_res.status_code == 200, create_res.text
    data = create_res.json()
    assert data["status"] == "active"
    assert data["field_name"] == "misconception_hypothesis"
    corr_id = data["id"]

    # 4. List corrections
    list_res = client.get(
        f"/api/v1/evaluations/findings/{finding.id}/corrections",
        headers=teacher_headers,
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == corr_id

    # 5. Teacher reverts correction
    revert_res = client.post(
        f"/api/v1/evaluations/findings/{finding.id}/corrections/{corr_id}/revert",
        headers=teacher_headers,
    )
    assert revert_res.status_code == 200
    rev_data = revert_res.json()
    assert rev_data["status"] == "reverted"


def test_severity_null_correction_and_revert(db_session: Session, correction_env):
    """
    GAP 5: Severity NULL correction & revert lifecycle:
    - Finding created with severity=None (AI omitted severity)
    - Teacher corrects to severity="high"
    - Verify: teacher_corrected=True, severity="high" visible downstream via resolver
    - Revert to AI
    - Verify: severity=None restored, correction status="reverted"
    """
    ctx = correction_env
    finding = EvaluationFinding(
        run_id=ctx["run"].id,
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.88,
        rationale="Omitted quotient rule denominator square",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        confidence_details={"score": 0.88, "level": "high", "uncertainty_reasons": []},
        misconceptions=[
            {
                "hypothesis": "Quotient rule denominator square missing",
                "evidence_excerpt": "f'g - fg'",
                "linked_concept": "Quotient Rule",
                "severity": None,  # AI omitted severity
            }
        ],
    )
    db_session.add(finding)
    db_session.commit()
    db_session.refresh(finding)

    # Pre-condition: original severity is None
    assert resolve_finding_field(finding, CorrectionFieldName.SEVERITY) is None
    assert finding.teacher_corrected is False

    # 1. Teacher applies correction: severity -> "high"
    corr = correction_service.apply_correction(
        db=db_session,
        finding_id=finding.id,
        field_name=CorrectionFieldName.SEVERITY,
        new_value="high",
        reason="Teacher evaluated omission as critical high-severity misconception.",
        teacher_id=ctx["teacher"].id,
    )
    db_session.refresh(finding)

    # Verify: teacher_corrected=True, severity="high" visible downstream
    assert corr.status == CorrectionStatus.ACTIVE.value
    assert corr.original_value is None
    assert corr.corrected_value == "high"
    assert finding.teacher_corrected is True
    assert resolve_finding_field(finding, CorrectionFieldName.SEVERITY) == "high"
    assert finding.misconceptions[0]["severity"] == "high"

    # 2. Revert to AI
    reverted_corr = correction_service.revert_to_ai(
        db=db_session,
        finding_id=finding.id,
        correction_id=corr.id,
        teacher_id=ctx["teacher"].id,
    )
    db_session.refresh(finding)

    # Verify: severity=None restored, correction status="reverted"
    assert reverted_corr.status == CorrectionStatus.REVERTED.value
    assert resolve_finding_field(finding, CorrectionFieldName.SEVERITY) is None
    assert finding.misconceptions[0]["severity"] is None
    assert finding.teacher_corrected is False
