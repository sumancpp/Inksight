import pytest
import uuid
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.assessment import Assessment, Question
from app.models.enums import (
    CorrectionFieldName,
    FindingCategory,
    FindingReviewStatus,
    UserRole,
)
from app.models.evaluation import EvaluationFinding, EvaluationRun
from app.models.submission import AnswerSheetUpload, QuestionAnswer, Submission
from app.models.topic import LearningTopic
from app.models.user import User
from app.schemas.correction import FindingCorrectionCreate
from scripts.seed_cluster_demo import seed_cluster_demo
from app.services.cluster_service import cluster_service
from app.services.correction_service import correction_service
from tests.conftest import auth_headers_for_user


@pytest.fixture
def cluster_env(db_session: Session):
    teacher = User(
        email=f"teacher_cluster_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Cluster Teacher",
        hashed_password="pw",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    students = [
        User(
            email=f"student_c_{i}_{uuid.uuid4().hex[:6]}@example.com",
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

    topic = LearningTopic(name="Calculus Clusters", description="Calculus")
    db_session.add(topic)
    db_session.commit()

    assessment = Assessment(title="Calculus Cluster Assessment", created_by=teacher.id)
    db_session.add(assessment)
    db_session.commit()

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Differentiate f(x) = (3x+1)^2",
        expected_answer="6(3x+1)",
        marks=5.0,
    )
    q2 = Question(
        assessment_id=assessment.id,
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
        "assessment": assessment,
        "topic": topic,
        "q1": q1,
        "q2": q2,
    }


def _create_sub_and_run(db_session: Session, assessment: Assessment, student: User, question: Question):
    sub = Submission(assessment_id=assessment.id, student_id=student.id, status="submitted")
    db_session.add(sub)
    db_session.commit()

    qa = QuestionAnswer(submission_id=sub.id, question_id=question.id, answer_text="test ans")
    db_session.add(qa)
    db_session.commit()

    run = EvaluationRun(
        submission_id=sub.id,
        question_id=question.id,
        question_answer_id=qa.id,
        evaluator_name="test_cluster_eval",
        status="completed",
        answer_text_hash=f"hash_{sub.id}_{question.id}_{uuid.uuid4().hex[:6]}",
        answer_text_snapshot="test ans",
    )
    db_session.add(run)
    db_session.commit()
    return sub, run


def test_seed_cluster_demo_script_and_idempotency(db_session: Session):
    """
    Note D & GAP 1: Tests seed_cluster_demo management function with production safety:
    - Run once: assert 2 clusters emerge with student_count=2 each.
    - Run twice without force on seeded assessment: raises ValueError refusing to overwrite.
    - Run twice with force=True: assert idempotent (no duplicate submissions/findings created).
    - Run with dry_run=True: assert no database writes occur.
    """
    # 1. First run (initial seed)
    assessment = seed_cluster_demo(db_session)
    res1 = cluster_service.get_misconception_clusters(db_session, assessment.id)

    assert len(res1.clusters) == 2
    assert res1.total_students_evaluated == 4
    assert res1.total_findings_evaluated == 4

    cluster_concepts = {c.linked_concept: c.student_count for c in res1.clusters}
    assert cluster_concepts["Fraction Division"] == 2
    assert cluster_concepts["Reverse Percentage"] == 2

    # 2. Refuses to overwrite without --force flag
    with pytest.raises(ValueError, match="already has 4 findings. Pass --force to proceed"):
        seed_cluster_demo(db_session, assessment_id=assessment.id, force=False)

    # 3. Second run with force=True (idempotency check)
    assessment2 = seed_cluster_demo(db_session, assessment_id=assessment.id, force=True)
    assert assessment2.id == assessment.id

    res2 = cluster_service.get_misconception_clusters(db_session, assessment.id)
    assert len(res2.clusters) == 2
    assert res2.total_students_evaluated == 4
    assert res2.total_findings_evaluated == 4
    for c in res2.clusters:
        assert c.student_count == 2
        assert len(c.finding_ids) == 2

    # 4. Dry-run safety test: no DB writes committed
    fresh_assessment = Assessment(
        title="Fresh Dry Run Assessment",
        description="Testing dry-run no-write safety",
        created_by=assessment.created_by,
    )
    db_session.add(fresh_assessment)
    db_session.commit()

    findings_count_before = db_session.query(EvaluationFinding).count()
    users_count_before = db_session.query(User).count()
    dry_run_assessment = seed_cluster_demo(
        db_session, assessment_id=fresh_assessment.id, dry_run=True
    )
    assert dry_run_assessment is not None
    findings_count_after = db_session.query(EvaluationFinding).count()
    users_count_after = db_session.query(User).count()
    assert findings_count_before == findings_count_after
    assert users_count_before == users_count_after


def test_cluster_threshold_single_student_two_findings_isolated_only(db_session: Session, cluster_env):
    """
    Note E: Minimum 2 DISTINCT students (not 2 findings — 2 students).
    If one student has 2 findings with the same linked_concept, that's 1 student -> NOT a cluster.
    """
    student = cluster_env["students"][0]
    assessment = cluster_env["assessment"]
    q1 = cluster_env["q1"]
    q2 = cluster_env["q2"]

    # Student 1 has finding on q1 with "Power Rule"
    sub1, run1 = _create_sub_and_run(db_session, assessment, student, q1)
    f1 = EvaluationFinding(
        run_id=run1.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Power Rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Error in power rule",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Subtracted 1 from coefficient",
            "evidence_excerpt": "3x^2",
            "linked_concept": "Power Rule",
            "severity": "medium",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )

    # Same Student 1 has finding on q2 also with "Power Rule"
    qa2 = QuestionAnswer(submission_id=sub1.id, question_id=q2.id, answer_text="ans 2")
    db_session.add(qa2)
    db_session.commit()
    run2 = EvaluationRun(
        submission_id=sub1.id,
        question_id=q2.id,
        question_answer_id=qa2.id,
        evaluator_name="eval2",
        status="completed",
        answer_text_hash=f"hash2_{sub1.id}_{q2.id}",
        answer_text_snapshot="ans 2",
    )
    db_session.add(run2)
    db_session.commit()

    f2 = EvaluationFinding(
        run_id=run2.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Power Rule",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Another power rule error",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Subtracted 1 from coefficient again",
            "evidence_excerpt": "4x^3",
            "linked_concept": "Power Rule",
            "severity": "medium",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add_all([f1, f2])
    db_session.commit()

    res = cluster_service.get_misconception_clusters(db_session, assessment.id)

    # Must NOT form a cluster because distinct students = 1
    assert len(res.clusters) == 0
    # Must be placed in isolated
    assert len(res.isolated) == 1
    assert res.isolated[0].linked_concept == "Power Rule"
    assert res.isolated[0].student_count == 1
    assert len(res.isolated[0].finding_ids) == 2


def test_cluster_with_corrected_linked_concept(client: TestClient, db_session: Session, cluster_env):
    """
    Note E: Two students, one finding each, same corrected linked_concept -> IS a cluster.
    Tests transitive Feature 2 resolver.
    """
    teacher = cluster_env["teacher"]
    student1 = cluster_env["students"][0]
    student2 = cluster_env["students"][1]
    assessment = cluster_env["assessment"]
    q1 = cluster_env["q1"]
    headers = auth_headers_for_user(teacher)

    # Student 1: AI marked as "Chain Rule"
    sub1, run1 = _create_sub_and_run(db_session, assessment, student1, q1)
    f1 = EvaluationFinding(
        run_id=run1.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Calculus",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Chain rule error",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Chain rule omission",
            "evidence_excerpt": "cos(x)",
            "linked_concept": "Chain Rule",
            "severity": "high",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add(f1)
    db_session.commit()

    # Student 2: already marked as "Quotient Rule"
    sub2, run2 = _create_sub_and_run(db_session, assessment, student2, q1)
    f2 = EvaluationFinding(
        run_id=run2.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Calculus",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Quotient rule error",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Quotient rule denominator missing square",
            "evidence_excerpt": "(u'v - uv')/v",
            "linked_concept": "Quotient Rule",
            "severity": "high",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add(f2)
    db_session.commit()

    # Before correction: both are isolated
    res_before = cluster_service.get_misconception_clusters(db_session, assessment.id)
    assert len(res_before.clusters) == 0
    assert len(res_before.isolated) == 2

    # Teacher corrects Student 1's linked_concept from "Chain Rule" to "Quotient Rule"
    corr_resp = client.post(
        f"/api/v1/evaluations/findings/{f1.id}/corrections",
        json={
            "field_name": "linked_concept",
            "corrected_value": "Quotient Rule",
            "correction_reason": "Actually a quotient rule error",
        },
        headers=headers,
    )
    assert corr_resp.status_code == 200

    # After correction: both students share "Quotient Rule" -> forms a cluster!
    res_after = cluster_service.get_misconception_clusters(db_session, assessment.id)
    assert len(res_after.clusters) == 1
    assert res_after.clusters[0].linked_concept == "Quotient Rule"
    assert res_after.clusters[0].student_count == 2
    assert set(res_after.clusters[0].student_ids) == {student1.id, student2.id}
    assert len(res_after.isolated) == 0


def test_cluster_splits_when_one_finding_corrected_to_distinct_concept(client: TestClient, db_session: Session, cluster_env):
    """
    Task B (GAP 5): Split behavior when one student's finding in a cluster is corrected to a distinct concept.
    - 2 students initially have same linked_concept="Fraction Division" -> forms 1 cluster (student_count=2).
    - Teacher corrects Student 2 to "Fractional Ratio".
    - Cluster API splits them: 0 clusters (neither has >= 2 students), 2 isolated items.
    - Verifies API returns corrected concept string ("Fractional Ratio") rather than original.
    - Behavior is intentionally SPLIT (safer): merging would falsely group distinct conceptual errors.
    """
    teacher = cluster_env["teacher"]
    student1 = cluster_env["students"][0]
    student2 = cluster_env["students"][1]
    assessment = cluster_env["assessment"]
    q1 = cluster_env["q1"]
    headers = auth_headers_for_user(teacher)

    # Student 1: "Fraction Division"
    sub1, run1 = _create_sub_and_run(db_session, assessment, student1, q1)
    f1 = EvaluationFinding(
        run_id=run1.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Mathematics",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Multiplied instead of inverted",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Direct numerator multiplication",
            "evidence_excerpt": "1/2 * 3/4 = 3/8",
            "linked_concept": "Fraction Division",
            "severity": "high",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add(f1)

    # Student 2: "Fraction Division"
    sub2, run2 = _create_sub_and_run(db_session, assessment, student2, q1)
    f2 = EvaluationFinding(
        run_id=run2.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Mathematics",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.9,
        rationale="Cross multiplied improperly",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Cross multiplication error",
            "evidence_excerpt": "1*4 / 2*3 = 4/6",
            "linked_concept": "Fraction Division",
            "severity": "medium",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add(f2)
    db_session.commit()

    # 1. Before correction: 1 class-wide cluster exists (2 students share "Fraction Division")
    res_before = client.get(
        f"/api/v1/analytics/assessments/{assessment.id}/misconception-clusters",
        headers=headers,
    )
    assert res_before.status_code == 200
    data_before = res_before.json()
    assert len(data_before["clusters"]) == 1
    assert data_before["clusters"][0]["linked_concept"] == "Fraction Division"
    assert data_before["clusters"][0]["student_count"] == 2
    assert len(data_before["isolated"]) == 0

    # 2. Teacher corrects Student 2 from "Fraction Division" -> "Fractional Ratio"
    corr_resp = client.post(
        f"/api/v1/evaluations/findings/{f2.id}/corrections",
        json={
            "field_name": "linked_concept",
            "corrected_value": "Fractional Ratio",
            "correction_reason": "Teacher noted student understood fraction division but misapplied part-to-whole ratio",
        },
        headers=headers,
    )
    assert corr_resp.status_code == 200

    # 3. After correction: cluster SPLITS because 1 corrected no longer matches 1 original
    res_after = client.get(
        f"/api/v1/analytics/assessments/{assessment.id}/misconception-clusters",
        headers=headers,
    )
    assert res_after.status_code == 200
    data_after = res_after.json()

    # Intended split behavior:
    # 0 clusters (neither concept reaches >= 2 distinct students threshold)
    assert len(data_after["clusters"]) == 0

    # 2 isolated items (each isolated to 1 student)
    assert len(data_after["isolated"]) == 2
    isolated_concepts = {item["linked_concept"]: item["student_count"] for item in data_after["isolated"]}
    assert isolated_concepts["Fraction Division"] == 1
    assert isolated_concepts["Fractional Ratio"] == 1

    # Verify API response returned the CORRECTED concept string
    corrected_item = next(item for item in data_after["isolated"] if item["linked_concept"] == "Fractional Ratio")
    assert corrected_item["student_ids"] == [student2.id]
    assert f2.id in corrected_item["finding_ids"]


def test_cluster_excludes_correct_understanding(db_session: Session, cluster_env):
    """
    Note E: Two students, one correct-by-AI (high conf) + one incorrect ->
    only incorrect student's finding in cluster/isolated, correct excluded.
    """
    student1 = cluster_env["students"][0]
    student2 = cluster_env["students"][1]
    assessment = cluster_env["assessment"]
    q1 = cluster_env["q1"]

    # Student 1: correct
    sub1, run1 = _create_sub_and_run(db_session, assessment, student1, q1)
    f1_correct = EvaluationFinding(
        run_id=run1.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Trig Substitution",
        category=FindingCategory.CORRECT_UNDERSTANDING.value,
        confidence=0.98,
        rationale="Student answered correctly.",
        verdict="correct",
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )

    # Student 2: incorrect
    sub2, run2 = _create_sub_and_run(db_session, assessment, student2, q1)
    f2_incorrect = EvaluationFinding(
        run_id=run2.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Trig Substitution",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.92,
        rationale="Forgot to change differential dt",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Forgot dt differential substitution",
            "evidence_excerpt": "dx = dt",
            "linked_concept": "Trig Substitution",
            "severity": "medium",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=False,
    )
    db_session.add_all([f1_correct, f2_incorrect])
    db_session.commit()

    res = cluster_service.get_misconception_clusters(db_session, assessment.id)

    # Student 1 is excluded from misconception cluster analysis
    # Student 2 is isolated (1 student, not a cluster)
    assert len(res.clusters) == 0
    assert len(res.isolated) == 1
    assert res.isolated[0].student_ids == [student2.id]


def test_cluster_excludes_unacknowledged_review_gate(db_session: Session, cluster_env):
    """
    Note E: One student requires_teacher_review=True + not acknowledged ->
    excluded entirely from cluster AND from isolated (won't show until reviewed).
    """
    student = cluster_env["students"][0]
    assessment = cluster_env["assessment"]
    q1 = cluster_env["q1"]

    sub, run = _create_sub_and_run(db_session, assessment, student, q1)
    f_unack = EvaluationFinding(
        run_id=run.id,
        topic_id=cluster_env["topic"].id,
        concept_name="Integration By Parts",
        category=FindingCategory.LIKELY_MISCONCEPTION.value,
        confidence=0.55,
        rationale="Low confidence finding",
        verdict="incorrect",
        misconceptions=[{
            "hypothesis": "Formula sign flip",
            "evidence_excerpt": "uv + int v du",
            "linked_concept": "Integration By Parts",
            "severity": "high",
        }],
        review_status=FindingReviewStatus.ACCEPTED.value,
        requires_teacher_review=True,
        acknowledged_uncertainty=False,  # NOT acknowledged
    )
    db_session.add(f_unack)
    db_session.commit()

    res = cluster_service.get_misconception_clusters(db_session, assessment.id)
    assert len(res.clusters) == 0
    assert len(res.isolated) == 0


def test_cluster_endpoint_teacher_auth_required(client: TestClient, db_session: Session, cluster_env):
    student = cluster_env["students"][0]
    teacher = cluster_env["teacher"]
    assessment = cluster_env["assessment"]

    # Student denied with 403
    resp_student = client.get(
        f"/api/v1/analytics/assessments/{assessment.id}/misconception-clusters",
        headers=auth_headers_for_user(student),
    )
    assert resp_student.status_code == 403

    # Teacher permitted with 200
    resp_teacher = client.get(
        f"/api/v1/analytics/assessments/{assessment.id}/misconception-clusters",
        headers=auth_headers_for_user(teacher),
    )
    assert resp_teacher.status_code == 200
    data = resp_teacher.json()
    assert "clusters" in data
    assert "isolated" in data
