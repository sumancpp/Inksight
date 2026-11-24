from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.user import User


def create_test_teacher(db: Session, email: str = "teacher@learngraph.edu", client: TestClient = None) -> User:
    """Helper to seed a teacher user for assessment creation."""
    user = User(
        full_name="Prof. Alan Turing",
        email=email,
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if client is not None:
        from tests.conftest import auth_headers_for_user
        client.headers.update(auth_headers_for_user(user))
    return user


# --- Learning Topics CRUD Tests ---


def test_topic_crud_flow(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "topic.teacher@example.com", client=client)

    # 1. Create Topic
    create_resp = client.post(
        "/api/v1/topics",
        json={"name": "Discrete Mathematics", "description": "Logic, sets, and graphs."},
    )
    assert create_resp.status_code == 201
    topic_data = create_resp.json()
    assert topic_data["name"] == "Discrete Mathematics"
    assert topic_data["description"] == "Logic, sets, and graphs."
    topic_id = topic_data["id"]

    # 2. Get Topic by ID
    get_resp = client.get(f"/api/v1/topics/{topic_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == topic_id

    # 3. List Topics with Pagination
    list_resp = client.get("/api/v1/topics?limit=10&offset=0")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert list_data["limit"] == 10
    assert list_data["offset"] == 0
    assert any(t["id"] == topic_id for t in list_data["items"])

    # 4. Patch Topic
    patch_resp = client.patch(
        f"/api/v1/topics/{topic_id}",
        json={"description": "Updated topic description."},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated topic description."
    assert patch_resp.json()["name"] == "Discrete Mathematics"

    # 5. Delete Topic
    del_resp = client.delete(f"/api/v1/topics/{topic_id}")
    assert del_resp.status_code == 204

    # 6. Verify Deletion (404)
    verify_resp = client.get(f"/api/v1/topics/{topic_id}")
    assert verify_resp.status_code == 404


def test_topic_validation_and_errors(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "topic.val@example.com", client=client)

    # Empty name should fail 422
    invalid_resp = client.post("/api/v1/topics", json={"name": ""})
    assert invalid_resp.status_code == 422

    # Non-existent topic 404
    missing_resp = client.get("/api/v1/topics/99999")
    assert missing_resp.status_code == 404

    # Patch non-existent topic 404
    patch_missing = client.patch("/api/v1/topics/99999", json={"name": "New Name"})
    assert patch_missing.status_code == 404

    # Delete non-existent topic 404
    del_missing = client.delete("/api/v1/topics/99999")
    assert del_missing.status_code == 404


# --- Assessments CRUD Tests ---


def test_assessment_crud_flow(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "turing@example.com", client=client)

    # 1. Create Assessment (created_by derived from token)
    create_resp = client.post(
        "/api/v1/assessments",
        json={
            "title": "Algorithms Quiz 1",
            "description": "Sorting and graph search algorithms",
        },
    )
    assert create_resp.status_code == 201
    assessment_data = create_resp.json()
    assert assessment_data["title"] == "Algorithms Quiz 1"
    assert assessment_data["created_by"] == teacher.id
    assessment_id = assessment_data["id"]

    # 2. Get Assessment by ID
    get_resp = client.get(f"/api/v1/assessments/{assessment_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == assessment_id

    # 3. List Assessments with Pagination
    list_resp = client.get("/api/v1/assessments?limit=5&offset=0")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(a["id"] == assessment_id for a in list_data["items"])

    # 4. Patch Assessment
    patch_resp = client.patch(
        f"/api/v1/assessments/{assessment_id}",
        json={"title": "Algorithms Quiz 1 (Revised)"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "Algorithms Quiz 1 (Revised)"

    # 5. Delete Assessment
    del_resp = client.delete(f"/api/v1/assessments/{assessment_id}")
    assert del_resp.status_code == 204

    # 6. Verify Deletion (404)
    verify_resp = client.get(f"/api/v1/assessments/{assessment_id}")
    assert verify_resp.status_code == 404


def test_assessment_validation_and_errors(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "val_teacher@example.com", client=client)

    # Missing required title fails 422
    resp_invalid = client.post("/api/v1/assessments", json={"description": "Missing title"})
    assert resp_invalid.status_code == 422

    # Non-existent assessment
    assert client.get("/api/v1/assessments/99999").status_code == 404
    assert client.patch("/api/v1/assessments/99999", json={"title": "X"}).status_code == 404
    assert client.delete("/api/v1/assessments/99999").status_code == 404


# --- Questions CRUD & Relations Tests ---


def test_question_crud_and_cascade(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "hopper@example.com", client=client)

    # 1. Setup Topic and Assessment
    topic_resp = client.post("/api/v1/topics", json={"name": "Calculus", "description": "Integrals"})
    topic_id = topic_resp.json()["id"]

    assess_resp = client.post(
        "/api/v1/assessments",
        json={"title": "Calculus Exam"},
    )
    assessment_id = assess_resp.json()["id"]

    # 2. Create Question under Assessment
    q_create_resp = client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={
            "topic_id": topic_id,
            "prompt": "Evaluate the integral of x dx from 0 to 1.",
            "question_type": "numerical",
            "marks": 5.0,
        },
    )
    assert q_create_resp.status_code == 201
    q_data = q_create_resp.json()
    assert q_data["prompt"] == "Evaluate the integral of x dx from 0 to 1."
    assert q_data["marks"] == 5.0
    assert q_data["assessment_id"] == assessment_id
    assert q_data["topic_id"] == topic_id
    question_id = q_data["id"]

    # 3. Get Question by ID
    get_q_resp = client.get(f"/api/v1/questions/{question_id}")
    assert get_q_resp.status_code == 200
    assert get_q_resp.json()["id"] == question_id

    # 4. List Questions under Assessment
    list_q_resp = client.get(f"/api/v1/assessments/{assessment_id}/questions")
    assert list_q_resp.status_code == 200
    list_q_data = list_q_resp.json()
    assert list_q_data["total"] == 1
    assert list_q_data["items"][0]["id"] == question_id

    # 5. Patch Question
    patch_q_resp = client.patch(
        f"/api/v1/questions/{question_id}",
        json={"marks": 10.0, "question_type": "short_answer"},
    )
    assert patch_q_resp.status_code == 200
    assert patch_q_resp.json()["marks"] == 10.0
    assert patch_q_resp.json()["question_type"] == "short_answer"

    # 6. Verify Conflict (409) when trying to delete topic referenced by question
    del_topic_resp = client.delete(f"/api/v1/topics/{topic_id}")
    assert del_topic_resp.status_code == 409
    err_msg = del_topic_resp.json()["error"]["message"]
    assert "referenced by 1 question(s)" in err_msg

    # 7. Delete Assessment should cascade-delete Question
    del_assess_resp = client.delete(f"/api/v1/assessments/{assessment_id}")
    assert del_assess_resp.status_code == 204

    # 8. Verify Question is cascade deleted (404)
    assert client.get(f"/api/v1/questions/{question_id}").status_code == 404

    # 9. Now that question is gone, topic can be deleted cleanly
    del_topic_now = client.delete(f"/api/v1/topics/{topic_id}")
    assert del_topic_now.status_code == 204


def test_question_validation_and_errors(client: TestClient, db_session: Session):
    teacher = create_test_teacher(db_session, "curie@example.com", client=client)

    topic_resp = client.post("/api/v1/topics", json={"name": "Physics", "description": "Mechanics"})
    topic_id = topic_resp.json()["id"]

    assess_resp = client.post(
        "/api/v1/assessments",
        json={"title": "Physics Quiz"},
    )
    assessment_id = assess_resp.json()["id"]

    # Create question with invalid question_type (422)
    invalid_type_resp = client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={"topic_id": topic_id, "prompt": "Question?", "question_type": "invalid_kind"},
    )
    assert invalid_type_resp.status_code == 422

    # Create question under non-existent assessment (404)
    missing_assess_resp = client.post(
        "/api/v1/assessments/99999/questions",
        json={"topic_id": topic_id, "prompt": "Question?", "question_type": "multiple_choice"},
    )
    assert missing_assess_resp.status_code == 404

    # Create question with non-existent topic (404)
    missing_topic_resp = client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={"topic_id": 99999, "prompt": "Question?", "question_type": "multiple_choice"},
    )
    assert missing_topic_resp.status_code == 404

    # List questions for non-existent assessment (404)
    assert client.get("/api/v1/assessments/99999/questions").status_code == 404

    # Get / Patch / Delete non-existent question (404)
    assert client.get("/api/v1/questions/99999").status_code == 404
    assert client.patch("/api/v1/questions/99999", json={"marks": 5.0}).status_code == 404
    assert client.delete("/api/v1/questions/99999").status_code == 404
