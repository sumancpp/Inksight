import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import QuestionType, SubmissionStatus, UserRole
from app.models.submission import QuestionAnswer, Submission
from app.models.user import User


def seed_entities(db: Session, client: TestClient = None):
    """Seed student, teacher, topic, assessment, and 2 questions."""
    teacher = User(
        full_name="Prof. Turing",
        email="turing.teach@learngraph.edu",
        role=UserRole.TEACHER.value,
    )
    student = User(
        full_name="Ada Lovelace",
        email="ada.student@learngraph.edu",
        role=UserRole.STUDENT.value,
    )
    db.add_all([teacher, student])
    db.commit()
    db.refresh(teacher)
    db.refresh(student)

    from app.models.topic import LearningTopic
    from app.models.assessment import Assessment, Question

    topic = LearningTopic(name="Calculus", description="Integration and derivatives")
    db.add(topic)
    db.commit()
    db.refresh(topic)

    assessment = Assessment(
        title="Calculus Quiz 1",
        description="Introductory quiz",
        created_by=teacher.id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    q1 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="What is d/dx of sin(x)?",
        question_type=QuestionType.SHORT_ANSWER.value,
        marks=5.0,
    )
    q2 = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Evaluate integral of 2x dx.",
        question_type=QuestionType.NUMERICAL.value,
        marks=10.0,
    )
    db.add_all([q1, q2])
    db.commit()
    db.refresh(q1)
    db.refresh(q2)

    if client is not None:
        from tests.conftest import auth_headers_for_user
        client.headers.update(auth_headers_for_user(student))

    return student, teacher, topic, assessment, q1, q2


def test_submission_lifecycle(client: TestClient, db_session: Session):
    student, teacher, topic, assessment, q1, q2 = seed_entities(db_session, client)

    # 1. Create a submission in draft status
    resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        json={"student_id": student.id, "status": "draft"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["assessment_id"] == assessment.id
    assert data["student_id"] == student.id
    assert data["status"] == "draft"
    assert data["submitted_at"] is None
    sub_id = data["id"]

    # 2. Get submission by ID
    get_resp = client.get(f"/api/v1/submissions/{sub_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == sub_id

    # 3. List submissions for assessment
    list_resp = client.get(f"/api/v1/assessments/{assessment.id}/submissions?limit=10&offset=0")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == sub_id

    # 4. Add answer for Question 1
    ans_resp = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "answer_text": "cos(x)", "awarded_marks": 5.0},
    )
    assert ans_resp.status_code == 201
    ans_data = ans_resp.json()
    assert ans_data["submission_id"] == sub_id
    assert ans_data["question_id"] == q1.id
    assert ans_data["answer_text"] == "cos(x)"
    assert ans_data["awarded_marks"] == 5.0
    ans_id = ans_data["id"]

    # 5. List answers for submission
    answers_list_resp = client.get(f"/api/v1/submissions/{sub_id}/answers")
    assert answers_list_resp.status_code == 200
    assert answers_list_resp.json()["total"] == 1
    assert answers_list_resp.json()["items"][0]["id"] == ans_id

    # 6. Update answer text and awarded marks
    patch_ans_resp = client.patch(
        f"/api/v1/submissions/{sub_id}/answers/{ans_id}",
        json={"answer_text": "cos(x) + C (not needed for derivative)", "awarded_marks": 4.5},
    )
    assert patch_ans_resp.status_code == 200
    assert patch_ans_resp.json()["awarded_marks"] == 4.5
    assert patch_ans_resp.json()["answer_text"] == "cos(x) + C (not needed for derivative)"

    # 7. Update submission status to 'submitted'
    patch_sub_resp = client.patch(
        f"/api/v1/submissions/{sub_id}",
        json={"status": "submitted"},
    )
    assert patch_sub_resp.status_code == 200
    assert patch_sub_resp.json()["status"] == "submitted"
    assert patch_sub_resp.json()["submitted_at"] is not None


def test_reject_duplicate_answers(client: TestClient, db_session: Session):
    student, teacher, topic, assessment, q1, _ = seed_entities(db_session, client)

    resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        json={"student_id": student.id},
    )
    sub_id = resp.json()["id"]

    # Add first answer
    resp1 = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "answer_text": "First answer"},
    )
    assert resp1.status_code == 201

    # Attempt to add duplicate answer for the same question
    resp2 = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "answer_text": "Duplicate answer"},
    )
    assert resp2.status_code == 409
    assert "already exists in submission" in resp2.json()["error"]["message"]


def test_reject_question_belonging_to_another_assessment(client: TestClient, db_session: Session):
    student, teacher, topic, assess1, q1, _ = seed_entities(db_session, client)

    from app.models.assessment import Assessment, Question

    # Create a second, unrelated assessment with a question
    assess2 = Assessment(title="Unrelated Assessment", created_by=teacher.id)
    db_session.add(assess2)
    db_session.commit()
    db_session.refresh(assess2)

    q_other = Question(
        assessment_id=assess2.id,
        topic_id=topic.id,
        prompt="Unrelated question",
        question_type=QuestionType.ESSAY.value,
        marks=10.0,
    )
    db_session.add(q_other)
    db_session.commit()
    db_session.refresh(q_other)

    # Submission for assess1
    resp = client.post(
        f"/api/v1/assessments/{assess1.id}/submissions",
        json={"student_id": student.id},
    )
    sub_id = resp.json()["id"]

    # Try to add q_other (from assess2) to sub_id (from assess1)
    ans_resp = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q_other.id, "answer_text": "Wrong assessment answer"},
    )
    assert ans_resp.status_code == 409
    assert "belongs to assessment" in ans_resp.json()["error"]["message"]


def test_reject_invalid_awarded_marks(client: TestClient, db_session: Session):
    student, _, _, assessment, q1, _ = seed_entities(db_session, client)
    # q1 max marks is 5.0

    resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        json={"student_id": student.id},
    )
    sub_id = resp.json()["id"]

    # Negative marks rejected by schema or endpoint (422)
    neg_resp = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "awarded_marks": -1.0},
    )
    assert neg_resp.status_code == 422

    # Marks exceeding question.marks (5.0) rejected with 422
    over_resp = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "awarded_marks": 5.5},
    )
    assert over_resp.status_code == 422
    assert "awarded_marks must be between 0.0 and 5.0" in over_resp.json()["error"]["message"]

    # Valid marks within range accepted
    valid_resp = client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "awarded_marks": 5.0},
    )
    assert valid_resp.status_code == 201
    ans_id = valid_resp.json()["id"]

    # Patch with excessive marks rejected with 422
    patch_over = client.patch(
        f"/api/v1/submissions/{sub_id}/answers/{ans_id}",
        json={"awarded_marks": 12.0},
    )
    assert patch_over.status_code == 422


def test_reject_invalid_status_and_missing_entities(client: TestClient, db_session: Session):
    student, _, _, assessment, _, _ = seed_entities(db_session, client)

    # Invalid status rejected with 422
    bad_status_resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        json={"student_id": student.id, "status": "invalid_status"},
    )
    assert bad_status_resp.status_code == 422

    # Non-existent assessment (404)
    missing_assess_resp = client.post(
        "/api/v1/assessments/99999/submissions",
        json={"student_id": student.id},
    )
    assert missing_assess_resp.status_code == 404

    # Non-existent student token (401/404)
    from app.core.security import create_access_token
    token_missing = create_access_token(subject="99999", role=UserRole.STUDENT.value)
    missing_student_resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        headers={"Authorization": f"Bearer {token_missing}"},
        json={"status": "draft"},
    )
    assert missing_student_resp.status_code in (401, 404)

    # Non-existent submission (404)
    assert client.get("/api/v1/submissions/99999").status_code == 404
    assert client.patch("/api/v1/submissions/99999", json={"status": "submitted"}).status_code == 404
    assert client.get("/api/v1/submissions/99999/answers").status_code == 404
    assert client.post("/api/v1/submissions/99999/answers", json={"question_id": 1}).status_code == 404


def test_cascade_deletion_of_submissions(client: TestClient, db_session: Session):
    student, teacher, topic, assessment, q1, _ = seed_entities(db_session, client)

    # Create submission and answer
    sub_resp = client.post(
        f"/api/v1/assessments/{assessment.id}/submissions",
        json={"student_id": student.id},
    )
    sub_id = sub_resp.json()["id"]

    client.post(
        f"/api/v1/submissions/{sub_id}/answers",
        json={"question_id": q1.id, "answer_text": "Sample answer"},
    )

    # Delete assessment (requires teacher auth)
    from tests.conftest import auth_headers_for_user
    del_resp = client.delete(
        f"/api/v1/assessments/{assessment.id}",
        headers=auth_headers_for_user(teacher),
    )
    assert del_resp.status_code == 204

    # Verify submission is gone
    assert client.get(f"/api/v1/submissions/{sub_id}").status_code == 404

    # Verify student is NOT deleted
    student_record = db_session.query(User).filter(User.id == student.id).first()
    assert student_record is not None
