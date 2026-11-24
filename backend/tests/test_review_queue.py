import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.assessment import Assessment, Question
from app.models.enums import (
    CorrectionFieldName,
    FindingCategory,
    FindingReviewStatus,
    ProposalStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.matching import ProposedAnswer
from app.models.ocr import OCRExtraction
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.correction import FindingCorrectionCreate
from app.services.correction_service import correction_service
from tests.conftest import auth_headers_for_user


@pytest.fixture
def queue_env(db_session: Session):
    teacher = User(
        email="queue_teacher@example.com",
        full_name="Queue Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    # Create 5 students for testing cross-student class-wide signals
    students = [
        User(
            email=f"queue_student_{i}@example.com",
            full_name=f"Student {i}",
            hashed_password="pw",
            role=UserRole.STUDENT.value,
            is_active=True,
        )
        for i in range(1, 6)
    ]
    db_session.add(teacher)
    db_session.add_all(students)
    db_session.commit()

    topic = LearningTopic(name="Calculus Rules", description="Calculus")
    db_session.add(topic)
    db_session.commit()

    assessment1 = Assessment(title="Calculus Quiz 1", created_by=teacher.id)
    assessment2 = Assessment(title="Calculus Quiz 2", created_by=teacher.id)
    db_session.add_all([assessment1, assessment2])
    db_session.commit()

    q1 = Question(
        assessment_id=assessment1.id,
        topic_id=topic.id,
        prompt="Differentiate f(x) = sin(x)*cos(x)",
        expected_answer="cos(2x)",
        marks=5.0,
    )
    q2 = Question(
        assessment_id=assessment1.id,
        topic_id=topic.id,
        prompt="Integrate g(x) = 2x",
        expected_answer="x^2 + C",
        marks=5.0,
    )
    db_session.add_all([q1, q2])
    db_session.commit()

    return {
        "teacher": teacher,
        "students": students,
        "assessment1": assessment1,
        "assessment2": assessment2,
        "topic": topic,
        "q1": q1,
        "q2": q2,
    }


def _create_submission_and_run(
    db_session: Session,
    assessment: Assessment,
    student: User,
    question: Question,
):
    sub = Submission(assessment_id=assessment.id, student_id=student.id, status="submitted")
    db_session.add(sub)
    db_session.commit()

    uid = uuid.uuid4().hex[:8]
    upload = AnswerSheetUpload(
        submission_id=sub.id,
        original_filename=f"sheet_{sub.id}.pdf",
        stored_filename=f"sheet_stored_{sub.id}_{uid}.pdf",
        storage_path=f"/tmp/sheet_{sub.id}_{uid}.pdf",
        content_type="application/pdf",
        file_size_bytes=1000,
        upload_status="completed",
    )
    db_session.add(upload)
    db_session.commit()

    qa = QuestionAnswer(submission_id=sub.id, question_id=question.id, answer_text="student ans")
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=sub.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="test_evaluator",
        status="completed",
        answer_text_hash=f"hash_{sub.id}_{question.id}",
        answer_text_snapshot="student ans",
    )
    db_session.add(run)
    db_session.commit()
    return sub, run, upload


def test_review_queue_filter_rules(client: TestClient, db_session: Session, queue_env):
    teacher = queue_env["teacher"]
    student = queue_env["students"][0]
    assessment = queue_env["assessment1"]
    q1 = queue_env["q1"]
    headers = auth_headers_for_user(teacher)

    sub, run, upload = _create_submission_and_run(db_session, assessment, student, q1)

    # 1. PENDING_REVIEW finding -> included
    f_pending = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Pending rationale",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=False,
        acknowledged_uncertainty=False,
    )
    # 2. ACCEPTED with requires_teacher_review=True and acknowledged=False -> included
    f_accepted_unack = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.6,
        rationale="Accepted unack rationale",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=False,
    )
    # 3. ACCEPTED with requires_teacher_review=False -> excluded
    f_accepted_clean = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.95,
        rationale="Accepted clean rationale",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
        acknowledged_uncertainty=False,
    )
    # 4. ACCEPTED with requires_teacher_review=True and acknowledged=True -> excluded
    f_accepted_ack = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.5,
        rationale="Accepted ack rationale",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=True,
    )
    # 5. SUPERSEDED finding -> excluded
    f_superseded = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.5,
        rationale="Superseded rationale",
        review_status=FindingReviewStatus.SUPERSEDED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=False,
    )

    db_session.add_all([
        f_pending,
        f_accepted_unack,
        f_accepted_clean,
        f_accepted_ack,
        f_superseded,
    ])
    db_session.commit()

    resp = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    finding_ids = [item["finding_id"] for item in data["items"]]
    assert f_pending.id in finding_ids
    assert f_accepted_unack.id in finding_ids
    assert f_accepted_clean.id not in finding_ids
    assert f_accepted_ack.id not in finding_ids
    assert f_superseded.id not in finding_ids


def test_review_queue_priority_scoring_breakdown(client: TestClient, db_session: Session, queue_env):
    teacher = queue_env["teacher"]
    student = queue_env["students"][0]
    assessment = queue_env["assessment1"]
    q1 = queue_env["q1"]
    headers = auth_headers_for_user(teacher)

    sub, run, upload = _create_submission_and_run(db_session, assessment, student, q1)

    # Attach a proposed answer with OCR confidence 0.72 (< 0.85 -> +20)
    ocr = OCRExtraction(
        upload_id=upload.id,
        extracted_text="student ocr answer",
        confidence=0.72,
        provider_name="mock_paddle",
        processing_status="completed",
    )
    db_session.add(ocr)
    db_session.commit()

    proposal = ProposedAnswer(
        submission_id=sub.id,
        upload_id=upload.id,
        ocr_extraction_id=ocr.id,
        question_id=q1.id,
        confidence=0.72,
        status=ProposalStatus.APPROVED.value,
        proposed_text="student ocr answer",
    )
    db_session.add(proposal)
    db_session.commit()

    # Finding with:
    # requires_teacher_review=True (+40)
    # misconception hypothesis (+30)
    # OCR confidence < 0.85 (+20)
    # category = INSUFFICIENT_EVIDENCE (+10)
    # 2 misconception items (+10)
    # Expected base priority = 40 + 30 + 20 + 10 + 10 = 110
    finding = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.INSUFFICIENT_EVIDENCE.value,
        confidence=0.55,
        rationale="Insufficient evidence rationale",
        confidence_details={"score": 0.55, "level": "low", "uncertainty_reasons": ["vague"]},
        requires_teacher_review=True,
        acknowledged_uncertainty=False,
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        misconception_hypothesis="Student confused differentiation and integration",
        misconceptions=[
            {
                "hypothesis": "Student confused differentiation and integration",
                "evidence_excerpt": "int sin(x) dx",
                "linked_concept": "Differentiation Rules",
                "severity": "high",
            },
            {
                "hypothesis": "Student omitted constant",
                "evidence_excerpt": "+ 0",
                "linked_concept": "Integration Constant",
                "severity": "low",
            },
        ],
    )
    db_session.add(finding)
    db_session.commit()

    resp = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    item = next(it for it in data["items"] if it["finding_id"] == finding.id)

    assert item["priority_score"] == 110
    assert "Requires teacher review flag (+40)" in item["priority_reasons"]
    assert "Misconception hypothesis detected (+30)" in item["priority_reasons"]
    assert "Low OCR extraction confidence (0.72 < 0.85) (+20)" in item["priority_reasons"]
    assert "Insufficient evidence category (+10)" in item["priority_reasons"]
    assert "2 misconception item(s) flagged (+10)" in item["priority_reasons"]
    assert item["question_number"] == 1
    assert item["student_name"] == "Student 1"


def test_review_queue_note_c_corrected_values_and_cross_student_signal(
    client: TestClient, db_session: Session, queue_env
):
    """
    Verifies Note C:
    - Finding created with 2 misconceptions.
    - Teacher corrects one misconception to have linked_concept="Product Rule".
    - 3 OTHER students in the same assessment also have linked_concept="Product Rule".
    - Priority endpoint must:
      1. Still apply +5 multiplier for 2 misconceptions (+10 total).
      2. Trigger the class-wide cross-student bonus (+15) using "Product Rule".
      3. For Note B: correcting confidence from low to high does NOT clear requires_teacher_review,
         so the +40 remains applied (as requires_teacher_review remains True).
    """
    teacher = queue_env["teacher"]
    students = queue_env["students"]
    assessment = queue_env["assessment1"]
    q1 = queue_env["q1"]
    headers = auth_headers_for_user(teacher)

    # Seed 3 OTHER students (students[1], students[2], students[3]) with "Product Rule"
    for i in range(1, 4):
        s_sub, s_run, s_upload = _create_submission_and_run(db_session, assessment, students[i], q1)
        s_f = EvaluationFinding(
            run_id=s_run.id,
            topic_id=queue_env["topic"].id,
            concept_name="Calculus",
            category=FindingCategory.LIKELY_MISCONCEPTION.value,
            confidence=0.8,
            rationale="Other student rationale",
            review_status=FindingReviewStatus.PENDING_REVIEW.value,
            requires_teacher_review=False,
            acknowledged_uncertainty=False,
            misconceptions=[
                {
                    "hypothesis": "Treated product of functions as sum of derivatives",
                    "evidence_excerpt": "f'*g'",
                    "linked_concept": "Product Rule",
                    "severity": "high",
                }
            ],
        )
        db_session.add(s_f)
    db_session.commit()

    # Target student (students[0]) has a finding with 2 misconceptions,
    # initially having linked_concept="Chain Rule" and low confidence (0.50 -> requires_teacher_review=True)
    target_student = students[0]
    target_sub, target_run, target_upload = _create_submission_and_run(db_session, assessment, target_student, q1)
    target_f = EvaluationFinding(
        run_id=target_run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Calculus",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.50,
        rationale="Target student rationale",
        confidence_details={"score": 0.50, "level": "low", "uncertainty_reasons": ["ambiguous"]},
        requires_teacher_review=True,
        acknowledged_uncertainty=False,
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        misconception_hypothesis="Student mistakenly applied chain rule instead of product rule",
        misconceptions=[
            {
                "hypothesis": "Mistakenly applied chain rule",
                "evidence_excerpt": "cos(sin(x))",
                "linked_concept": "Chain Rule",
                "severity": "medium",
            },
            {
                "hypothesis": "Algebraic sign omission",
                "evidence_excerpt": "- sin",
                "linked_concept": "Trig Signs",
                "severity": "low",
            },
        ],
    )
    db_session.add(target_f)
    db_session.commit()

    # Before correction:
    # - requires_teacher_review = True (+40)
    # - misconception hypothesis exists (+30)
    # - 2 misconceptions (+10)
    # - Chain Rule does NOT appear in >= 3 other students (0 others) -> no bonus
    # Base score = 40 + 30 + 10 = 80
    resp_before = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}",
        headers=headers,
    )
    assert resp_before.status_code == 200
    item_before = next(it for it in resp_before.json()["items"] if it["finding_id"] == target_f.id)
    assert item_before["priority_score"] == 80

    # 1. Teacher corrects linked_concept to "Product Rule" via correction service
    corr_resp = client.post(
        f"/api/v1/evaluations/findings/{target_f.id}/corrections",
        json={
            "field_name": "linked_concept",
            "corrected_value": "Product Rule",
            "correction_reason": "Clear product rule error, not chain rule",
        },
        headers=headers,
    )
    assert corr_resp.status_code == 200

    # Now call priority endpoint:
    # - 2 misconceptions count still applies (+10)
    # - Cross-student class-wide signal triggers for "Product Rule" (+15)
    # Expected score = 40 + 30 + 10 + 15 = 95
    resp_after = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}",
        headers=headers,
    )
    assert resp_after.status_code == 200
    item_after = next(it for it in resp_after.json()["items"] if it["finding_id"] == target_f.id)
    assert item_after["priority_score"] == 95
    assert any("Class-wide misconception: 'Product Rule' shared with 3 other students (+15)" in r for r in item_after["priority_reasons"])
    assert "2 misconception item(s) flagged (+10)" in item_after["priority_reasons"]
    assert item_after["teacher_corrected"] is True

    # 2. Teacher corrects confidence from low (0.50) to high (0.95) per Note B
    # Note B semantics:
    # Correcting confidence from low to high recomputes confidence_details.level to 'high',
    # but does NOT auto-clear requires_teacher_review (requires_teacher_review stays True until explicit teacher review).
    # Therefore, the +40 requires_teacher_review still applies (it is NOT lost or gained anew).
    corr_conf_resp = client.post(
        f"/api/v1/evaluations/findings/{target_f.id}/corrections",
        json={
            "field_name": "confidence_score",
            "corrected_value": 0.95,
            "correction_reason": "Teacher verified confidence is actually high",
        },
        headers=headers,
    )
    assert corr_conf_resp.status_code == 200

    resp_after_conf = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}",
        headers=headers,
    )
    assert resp_after_conf.status_code == 200
    item_after_conf = next(it for it in resp_after_conf.json()["items"] if it["finding_id"] == target_f.id)
    # Priority retains the +40 because requires_teacher_review remains True per Note B
    assert item_after_conf["priority_score"] == 95
    assert "Requires teacher review flag (+40)" in item_after_conf["priority_reasons"]


def test_review_queue_pagination_and_sorting(client: TestClient, db_session: Session, queue_env):
    teacher = queue_env["teacher"]
    student = queue_env["students"][0]
    assessment = queue_env["assessment1"]
    q1 = queue_env["q1"]
    headers = auth_headers_for_user(teacher)

    sub, run, upload = _create_submission_and_run(db_session, assessment, student, q1)

    # Create 3 findings with varying scores
    f1 = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Rationale 1",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=False,
    )  # Score = 0
    f2 = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.5,
        rationale="Rationale 2",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=True,
    )  # Score = 40
    f3 = EvaluationFinding(
        run_id=run.id,
        topic_id=queue_env["topic"].id,
        concept_name="Derivatives",
        category=FindingCategory.INSUFFICIENT_EVIDENCE.value,
        confidence=0.5,
        rationale="Rationale 3",
        review_status=FindingReviewStatus.PENDING_REVIEW.value,
        requires_teacher_review=True,
        misconception_hypothesis="Hypothesis exists",
    )  # Score = 40 + 30 + 10 + 5 = 85

    db_session.add_all([f1, f2, f3])
    db_session.commit()

    # Query with sort=priority, page_size=2
    resp = client.get(
        f"/api/v1/evaluations/pending-review?assessment_id={assessment.id}&page=1&page_size=2&sort=priority",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["finding_id"] == f3.id
    assert data["items"][0]["priority_score"] >= data["items"][1]["priority_score"]


def test_review_queue_teacher_auth_required(client: TestClient, db_session: Session, queue_env):
    student = queue_env["students"][0]
    student_headers = auth_headers_for_user(student)

    # Student cannot access teacher review queue
    resp = client.get("/api/v1/evaluations/pending-review", headers=student_headers)
    assert resp.status_code == 403
