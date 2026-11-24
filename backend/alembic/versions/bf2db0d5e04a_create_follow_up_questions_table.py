"""create_follow_up_questions_table

Revision ID: bf2db0d5e04a
Revises: 74ff18316c0b
Create Date: 2026-11-08 23:35:18.659563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf2db0d5e04a'
down_revision: Union[str, Sequence[str], None] = '74ff18316c0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "follow_up_questions" not in tables:
        op.create_table(
            "follow_up_questions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("finding_id", sa.Integer(), sa.ForeignKey("evaluation_findings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("concept", sa.String(length=255), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=False),
            sa.Column("expected_answer", sa.Text(), nullable=False),
            sa.Column("rubric", sa.JSON(), nullable=False),
            sa.Column("question_type", sa.String(length=50), nullable=False, server_default="short_answer"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="proposed"),
            sa.Column("proposed_by", sa.String(length=50), nullable=False, server_default="system"),
            sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("audit_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.create_index(op.f("ix_follow_up_questions_id"), "follow_up_questions", ["id"], unique=False)
        op.create_index(op.f("ix_follow_up_questions_finding_id"), "follow_up_questions", ["finding_id"], unique=False)
        op.create_index(op.f("ix_follow_up_questions_assessment_id"), "follow_up_questions", ["assessment_id"], unique=False)
        op.create_index(op.f("ix_follow_up_questions_status"), "follow_up_questions", ["status"], unique=False)
        op.create_index(op.f("ix_follow_up_questions_approved_by"), "follow_up_questions", ["approved_by"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "follow_up_questions" in tables:
        op.drop_index(op.f("ix_follow_up_questions_approved_by"), table_name="follow_up_questions")
        op.drop_index(op.f("ix_follow_up_questions_status"), table_name="follow_up_questions")
        op.drop_index(op.f("ix_follow_up_questions_assessment_id"), table_name="follow_up_questions")
        op.drop_index(op.f("ix_follow_up_questions_finding_id"), table_name="follow_up_questions")
        op.drop_index(op.f("ix_follow_up_questions_id"), table_name="follow_up_questions")
        op.drop_table("follow_up_questions")
