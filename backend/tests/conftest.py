import os
import tempfile
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def configure_celery_test_mode(monkeypatch):
    """Ensure no background tasks are executed during tests; Celery runs eagerly in-memory."""
    from app.core.celery_app import celery_app
    from app.core.config import settings

    monkeypatch.setattr(settings, "CELERY_TASK_ALWAYS_EAGER", True)
    monkeypatch.setattr(settings, "CELERY_BROKER_URL", "memory://")
    monkeypatch.setattr(settings, "CELERY_RESULT_BACKEND", "cache+memory://")
    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=True,
    )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provides an isolated SQLite database session with foreign keys enabled."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()
    db_url = f"sqlite:///{temp_file.name}"

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(test_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Fixture providing a FastAPI TestClient bound to the isolated db_session."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers_for_user(user) -> dict:
    from app.core.security import create_access_token
    token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "email": user.email,
        },
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers():
    """Fixture returning a callable that generates auth headers for any User instance."""
    return auth_headers_for_user


@pytest.fixture(autouse=True)
def default_test_settings(monkeypatch):
    """
    Ensures unit tests run deterministically with mock evaluator by default,
    avoiding external network dependencies unless a test explicitly configures vllm.
    """
    from app.core.config import settings
    monkeypatch.setattr(settings, "EVALUATOR_PROVIDER", "mock")

