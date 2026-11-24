"""
Unit and integration tests for Celery background worker and task-status endpoints.
"""
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.models.enums import UserRole
from app.models.user import User
from app.models.assessment import Assessment
from app.models.submission import Submission
from tests.conftest import auth_headers_for_user


def test_celery_app_configuration():
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_store_eager_result is True
    assert celery_app.conf.task_serializer == "json"


def test_async_evaluate_and_task_status_flow(client: TestClient, db_session: Session):
    teacher = User(
        full_name="Dr. Celery Teacher",
        email="celery.teacher@inksight.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    db_session.add(teacher)
    db_session.commit()

    assessment = Assessment(
        title="Async Celery Assessment",
        description="Testing Celery queue",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.commit()

    submission = Submission(
        assessment_id=assessment.id,
        student_id=teacher.id,
        status="submitted",
    )
    db_session.add(submission)
    db_session.commit()

    headers = auth_headers_for_user(teacher)

    # 1. Dispatch async evaluation -> 202 Accepted with task_id
    resp = client.post(
        f"/api/v1/submissions/{submission.id}/evaluate",
        headers=headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "ACCEPTED"
    assert data["submission_id"] == submission.id

    task_id = data["task_id"]

    # 2. Poll task status endpoint
    status_resp = client.get(
        f"/api/v1/submissions/task-status/{task_id}",
        headers=headers,
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["task_id"] == task_id
    assert status_data["status"] == "SUCCESS"
    assert status_data["ready"] is True
    assert status_data["successful"] is True
    assert "findings" in status_data
    assert "result" in status_data


def test_task_status_failure_reporting(client: TestClient, db_session: Session, monkeypatch):
    teacher = User(
        full_name="Dr. Failure Teacher",
        email="failure.teacher@inksight.edu",
        role=UserRole.TEACHER.value,
        is_active=True,
    )
    db_session.add(teacher)
    db_session.commit()
    headers = auth_headers_for_user(teacher)

    from celery.result import AsyncResult

    mock_res = MagicMock()
    mock_res.state = "FAILURE"
    mock_res.result = Exception("Mock LLM Evaluation Timeout")

    monkeypatch.setattr("celery.result.AsyncResult", lambda task_id, app: mock_res)

    status_resp = client.get(
        "/api/v1/submissions/task-status/mock-failure-id",
        headers=headers,
    )
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "FAILURE"
    assert data["successful"] is False
    assert "Mock LLM Evaluation Timeout" in data["error"]
