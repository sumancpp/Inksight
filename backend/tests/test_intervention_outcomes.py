import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
def outcomes_setup(db_session: Session):
    teacher = User(
        full_name="Prof. Euler",
        email="euler@learngraph.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    alice = User(
        full_name="Alice Learner",
        email="alice.outcomes@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    bob = User(
        full_name="Bob Learner",
        email="bob.outcomes@learngraph.edu",
        role=UserRole.STUDENT.value,
        is_active=True,
    )
    db_session.add_all([teacher, alice, bob])
    db_session.commit()

    topic = LearningTopic(
        name="Calculus Limits",
        description="Understanding limit definitions and evaluation techniques",
    )
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(
        title="Midterm Calculus Exam",
        description="Limits and Continuity",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Evaluate the limit of (x^2 - 1)/(x - 1) as x approaches 1.",
        question_type=QuestionType.SHORT_ANSWER.value,
        expected_answer="2",
        rubric="Factor numerator as (x-1)(x+1), cancel (x-1), evaluate 1+1 = 2.",
        marks=5.0,
    )
    db_session.add(question)
    db_session.commit()

    sub_alice = Submission(
        assessment_id=assessment.id,
        student_id=alice.id,
        status=SubmissionStatus.REVIEWED.value,
    )
    db_session.add(sub_alice)
    db_session.commit()

    qa = QuestionAnswer(
        submission_id=sub_alice.id,
        question_id=question.id,
        answer_text="The limit is 0/0 which is undefined.",
    )
    db_session.add(qa)
    db_session.commit()

    eval_run = EvaluationRun(
        submission_id=sub_alice.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="mock_evaluator",
        status=EvaluationStatus.COMPLETED.value,
        answer_text_hash="hash_alice_lim",
        answer_text_snapshot=qa.answer_text,
    )
    db_session.add(eval_run)
    db_session.commit()

    finding = EvaluationFinding(
        run_id=eval_run.id,
        topic_id=topic.id,
        concept_name="Indeterminate Forms & Algebraic Cancellation",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        uncertainty_rationale="High confidence based on direct statement that 0/0 is undefined without factoring.",
        evidence_excerpt="The limit is 0/0 which is undefined.",
        rationale="Student treated 0/0 indeterminate form as immediately undefined rather than simplifying algebraically.",
        review_status=FindingReviewStatus.ACCEPTED.value,
        reviewed_by=teacher.id,
        review_notes="Confirmed conceptual gap regarding indeterminate forms",
    )
    db_session.add(finding)
    db_session.commit()

    remed_run = RemediationRun(
        finding_id=finding.id,
        evaluation_run_id=eval_run.id,
        generator_name="mock_remediation_generator",
        status=RemediationRunStatus.COMPLETED.value,
    )
    db_session.add(remed_run)
    db_session.commit()

    # Approved follow-up items
    item1 = RemediationItem(
        run_id=remed_run.id,
        finding_id=finding.id,
        target_concept="Indeterminate Forms & Algebraic Cancellation",
        question_text="Evaluate the limit of (x^2 - 4)/(x - 2) as x approaches 2.",
        question_type=PracticeQuestionType.SHORT_ANSWER.value,
        teacher_answer_key="4",
        teacher_rationale="Reinforces factoring (x-2)(x+2) and algebraic cancellation.",
        difficulty="medium",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
        review_notes="Approved for student delivery",
    )
    item2 = RemediationItem(
        run_id=remed_run.id,
        finding_id=finding.id,
        target_concept="Indeterminate Forms & Algebraic Cancellation",
        question_text="Explain why 0/0 is called an indeterminate form rather than undefined.",
        question_type=PracticeQuestionType.EXPLAIN_REASONING.value,
        teacher_answer_key="Because different functions with limit 0/0 can evaluate to different real values.",
        teacher_rationale="Tests conceptual definition of indeterminate forms.",
        difficulty="hard",
        review_status=PracticeItemReviewStatus.APPROVED.value,
        reviewed_by=teacher.id,
        review_notes="Approved for student delivery",
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    return {
        "teacher": teacher,
        "alice": alice,
        "bob": bob,
        "assessment": assessment,
        "topic": topic,
        "sub_alice": sub_alice,
        "finding": finding,
        "item1": item1,
        "item2": item2,
    }


def test_intervention_outcomes_learning_loop(client: TestClient, outcomes_setup, db_session: Session):
    """
    Test learning loop progression across follow-up evidence collection:
    1. Pending Follow-up: 0 practice responses -> outcome_status is 'pending_followup', uncertainty is 'High'.
    2. Single Response: 1 correct response -> outcome_status is 'uncertain' (Tentative Progress),
       explicitly avoiding premature claims of mastery.
    3. Multiple Responses: 2 correct responses -> outcome_status transitions to 'improved', uncertainty decreases.
    4. Teacher sees full intervention details with audit provenance.
    """
    teacher = outcomes_setup["teacher"]
    alice = outcomes_setup["alice"]
    sub_alice = outcomes_setup["sub_alice"]
    finding = outcomes_setup["finding"]
    item1 = outcomes_setup["item1"]
    item2 = outcomes_setup["item2"]

    t_headers = auth_headers_for_user(teacher)
    a_headers = auth_headers_for_user(alice)

    # 1. Initially 0 practice responses: Check Teacher Intervention Outcomes
    r_initial = client.get(
        f"/api/v1/submissions/{sub_alice.id}/intervention-outcomes",
        headers=t_headers,
    )
    assert r_initial.status_code == 200
    data_init = r_initial.json()
    assert data_init["total_interventions"] == 1
    assert data_init["pending_count"] == 1
    assert data_init["improved_count"] == 0

    outcome0 = data_init["outcomes"][0]
    assert outcome0["outcome_status"] == "pending_followup"
    assert outcome0["uncertainty_level"] == "High"
    assert outcome0["evidence_count"] == 0
    assert "Awaiting student practice" in outcome0["performance_comparison"]

    # 2. Alice starts practice session
    r_start = client.post(
        f"/api/v1/submissions/{sub_alice.id}/practice-sessions",
        headers=a_headers,
    )
    assert r_start.status_code == 201
    sess_id = r_start.json()["id"]

    # Alice submits 1 correct answer to item1
    r_sub1 = client.post(
        f"/api/v1/practice-sessions/{sess_id}/responses",
        headers=a_headers,
        json={"remediation_item_id": item1.id, "student_answer": "4"},
    )
    assert r_sub1.status_code == 201
    assert r_sub1.json()["is_correct"] is True

    # Check Teacher Outcomes after 1 response -> MUST be UNCERTAIN (single response disclaimer)
    r_after1 = client.get(
        f"/api/v1/submissions/{sub_alice.id}/intervention-outcomes",
        headers=t_headers,
    )
    assert r_after1.status_code == 200
    data_after1 = r_after1.json()
    assert data_after1["uncertain_count"] == 1
    assert data_after1["improved_count"] == 0  # CRITICAL: Does not claim mastery from single response!

    outcome1 = data_after1["outcomes"][0]
    assert outcome1["outcome_status"] == "uncertain"
    assert outcome1["evidence_count"] == 1
    assert outcome1["correct_count"] == 1
    assert "Single correct response" in outcome1["uncertainty_rationale"]
    assert "insufficient to certify mastery" in outcome1["uncertainty_rationale"]

    # 3. Alice submits 2nd correct answer to item2
    r_sub2 = client.post(
        f"/api/v1/practice-sessions/{sess_id}/responses",
        headers=a_headers,
        json={
            "remediation_item_id": item2.id,
            "student_answer": "Different functions with limit 0/0 evaluate to different real values.",
        },
    )
    assert r_sub2.status_code == 201

    # Check Teacher Outcomes after 2 responses -> Transitions to IMPROVED
    r_after2 = client.get(
        f"/api/v1/submissions/{sub_alice.id}/intervention-outcomes",
        headers=t_headers,
    )
    assert r_after2.status_code == 200
    data_after2 = r_after2.json()
    assert data_after2["improved_count"] == 1
    assert data_after2["uncertain_count"] == 0

    outcome2 = data_after2["outcomes"][0]
    assert outcome2["outcome_status"] == "improved"
    assert outcome2["evidence_count"] == 2
    assert outcome2["correct_count"] == 2
    assert outcome2["accuracy_percentage"] == 100.0
    assert outcome2["uncertainty_level"] in ("Low", "Low-Moderate")
    assert "Demonstrated Improvement" in outcome2["outcome_label"]


def test_student_progress_report_privacy_and_access(client: TestClient, outcomes_setup):
    """
    Test student-facing learning loop progress report:
    - Alice receives topic-wise progress with baseline gaps, evidence count, remaining gaps, and next step.
    - STRICT PRIVACY GUARANTEE: Student view NEVER leaks teacher_answer_key, teacher_rationale, or review_notes.
    - Bob (unauthorized student) cannot access Alice's report (403 Forbidden).
    - Unauthenticated request returns 401 Unauthorized.
    """
    alice = outcomes_setup["alice"]
    bob = outcomes_setup["bob"]
    sub_alice = outcomes_setup["sub_alice"]

    a_headers = auth_headers_for_user(alice)
    b_headers = auth_headers_for_user(bob)

    # Alice requests her student progress report
    resp = client.get(
        f"/api/v1/submissions/{sub_alice.id}/student-progress",
        headers=a_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["submission_id"] == sub_alice.id
    assert "concepts" in data
    assert len(data["concepts"]) == 1

    concept = data["concepts"][0]
    assert concept["concept_name"] == "Indeterminate Forms & Algebraic Cancellation"
    assert "Initial diagnostic assessment" in concept["baseline_diagnostic_gap"]
    assert concept["recommended_next_step"] != ""
    assert "Formative learning evidence" in data["pedagogical_disclaimer"]

    # STRICT PRIVACY ASSERTIONS: Inspect raw JSON string
    raw_json = resp.text
    assert "teacher_answer_key" not in raw_json
    assert "teacher_rationale" not in raw_json
    assert "review_notes" not in raw_json
    assert "Confirmed conceptual gap regarding indeterminate forms" not in raw_json

    # Bob tries to access Alice's report -> 403 Forbidden
    r_bob = client.get(
        f"/api/v1/submissions/{sub_alice.id}/student-progress",
        headers=b_headers,
    )
    assert r_bob.status_code == 403
    assert "Not authorized" in get_error_message(r_bob)

    # Unauthenticated -> 401 Unauthorized
    r_unauth = client.get(f"/api/v1/submissions/{sub_alice.id}/student-progress")
    assert r_unauth.status_code == 401


def test_assessment_intervention_outcomes(client: TestClient, outcomes_setup):
    """
    Test aggregating intervention outcomes across an assessment:
    - Teacher retrieves assessment-wide outcomes.
    - Non-teacher student is rejected with 403 Forbidden.
    """
    teacher = outcomes_setup["teacher"]
    bob = outcomes_setup["bob"]
    assessment = outcomes_setup["assessment"]

    t_headers = auth_headers_for_user(teacher)
    b_headers = auth_headers_for_user(bob)

    # Teacher accesses assessment outcomes
    resp = client.get(
        f"/api/v1/assessments/{assessment.id}/intervention-outcomes",
        headers=t_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assessment_id"] == assessment.id
    assert "total_interventions" in data
    assert "outcomes" in data

    # Student Bob tries to access teacher intervention outcomes -> 403 Forbidden
    r_student = client.get(
        f"/api/v1/assessments/{assessment.id}/intervention-outcomes",
        headers=b_headers,
    )
    assert r_student.status_code == 403


def test_missing_entities_error_handling(client: TestClient, outcomes_setup):
    """Test 404 behavior for non-existent submission or assessment."""
    teacher = outcomes_setup["teacher"]
    t_headers = auth_headers_for_user(teacher)

    r_sub = client.get("/api/v1/submissions/999999/intervention-outcomes", headers=t_headers)
    assert r_sub.status_code == 404

    r_prog = client.get("/api/v1/submissions/999999/student-progress", headers=t_headers)
    assert r_prog.status_code == 404

    r_asmt = client.get("/api/v1/assessments/999999/intervention-outcomes", headers=t_headers)
    assert r_asmt.status_code == 404
