import os
import tempfile
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Assessment, LearningTopic, Question, QuestionType, User, UserRole
from app.schemas import QuestionCreate, UserCreate


def test_alembic_migration_lifecycle():
    """Verify that Alembic migrations run upgrade and downgrade cleanly."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()
    db_url = f"sqlite:///{temp_file.name}"

    try:
        backend_dir = Path(__file__).resolve().parent.parent
        alembic_ini_path = backend_dir / "alembic.ini"

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

        # 1. Apply upgrade to head
        command.upgrade(alembic_cfg, "head")

        from sqlalchemy import create_engine
        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        expected_tables = {
            "users",
            "learning_topics",
            "assessments",
            "questions",
            "submissions",
            "question_answers",
            "answer_sheet_uploads",
            "ocr_extractions",
            "proposed_answers",
            "teacher_reviews",
            "evaluation_runs",
            "evaluation_findings",
            "finding_review_audits",
            "remediation_runs",
            "remediation_items",
            "remediation_item_audits",
            "alembic_version",
        }

        assert expected_tables.issubset(tables), f"Expected tables {expected_tables} to exist, found {tables}"



        # 2. Test downgrade to base
        command.downgrade(alembic_cfg, "base")
        inspector = inspect(engine)
        remaining_tables = set(inspector.get_table_names())
        assert not {
            "users",
            "learning_topics",
            "assessments",
            "questions",
            "submissions",
            "question_answers",
            "answer_sheet_uploads",
        }.intersection(remaining_tables)
        engine.dispose()
    finally:
        if os.path.exists(temp_file.name):
            os.remove(temp_file.name)


def test_user_email_uniqueness(db_session: Session):
    """Verify that user email uniqueness constraint is enforced."""
    user1 = User(
        full_name="Alice Smith",
        email="alice@example.com",
        role=UserRole.STUDENT.value,
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        full_name="Alice Duplicate",
        email="alice@example.com",
        role=UserRole.TEACHER.value,
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_schema_role_validation():
    """Verify Pydantic schema accepts valid roles and rejects invalid ones."""
    # Valid roles
    for valid_role in [UserRole.STUDENT, UserRole.TEACHER, UserRole.ADMIN, "student", "teacher", "admin"]:
        user_data = UserCreate(
            full_name="Test User",
            email="test@example.com",
            role=valid_role,
        )
        assert user_data.role in [UserRole.STUDENT, UserRole.TEACHER, UserRole.ADMIN]

    # Invalid role
    with pytest.raises(ValidationError):
        UserCreate(
            full_name="Invalid Role User",
            email="invalid@example.com",
            role="superhero",  # Invalid role
        )


def test_question_schema_type_validation():
    """Verify Pydantic schema accepts valid question types and rejects invalid ones."""
    for valid_type in [
        QuestionType.MULTIPLE_CHOICE,
        QuestionType.SHORT_ANSWER,
        QuestionType.NUMERICAL,
        QuestionType.ESSAY,
        "multiple_choice",
    ]:
        q_data = QuestionCreate(
            assessment_id=1,
            topic_id=1,
            prompt="What is 2 + 2?",
            question_type=valid_type,
            marks=2.0,
        )
        assert q_data.marks == 2.0

    with pytest.raises(ValidationError):
        QuestionCreate(
            assessment_id=1,
            topic_id=1,
            prompt="Invalid type question",
            question_type="unsupported_type",
        )


def test_assessment_and_question_relationships(db_session: Session):
    """Verify foreign keys and relationship navigation across entities."""
    # 1. Create a teacher
    teacher = User(
        full_name="Prof. Johnson",
        email="johnson@example.com",
        role=UserRole.TEACHER.value,
    )
    db_session.add(teacher)
    db_session.flush()

    # 2. Create a learning topic
    topic = LearningTopic(
        name="Linear Algebra",
        description="Matrices, vectors, and eigenvalues",
    )
    db_session.add(topic)
    db_session.flush()

    # 3. Create an assessment created by the teacher
    assessment = Assessment(
        title="Midterm Assessment",
        description="Comprehensive review test",
        created_by=teacher.id,
    )
    db_session.add(assessment)
    db_session.flush()

    # 4. Add a question linked to assessment and topic
    question = Question(
        assessment_id=assessment.id,
        topic_id=topic.id,
        prompt="Find the determinant of matrix A.",
        question_type=QuestionType.NUMERICAL.value,
        marks=5.0,
    )
    db_session.add(question)
    db_session.commit()

    # 5. Verify relationship navigation
    db_session.refresh(assessment)
    db_session.refresh(topic)
    db_session.refresh(teacher)

    assert len(teacher.assessments) == 1
    assert teacher.assessments[0].title == "Midterm Assessment"
    assert len(assessment.questions) == 1
    assert assessment.questions[0].prompt == "Find the determinant of matrix A."
    assert assessment.questions[0].topic.name == "Linear Algebra"
    assert len(topic.questions) == 1

    # 6. Verify cascade deletion of questions when assessment is deleted
    db_session.delete(assessment)
    db_session.commit()

    deleted_question = db_session.query(Question).filter_by(id=question.id).first()
    assert deleted_question is None


def test_foreign_key_constraints(db_session: Session):
    """Verify foreign key enforcement when referencing non-existent records."""
    # Attempt to create question with non-existent assessment and topic
    orphan_question = Question(
        assessment_id=9999,
        topic_id=9999,
        prompt="Invalid FK question",
        marks=1.0,
    )
    db_session.add(orphan_question)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
