"""add_missing_columns_to_sync_models

Revision ID: 0a36ff46b8b1
Revises: 9e068246382b
Create Date: 2026-11-24 21:17:37.187390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a36ff46b8b1'
down_revision: Union[str, Sequence[str], None] = '9e068246382b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema idempotently with missing columns for uploads, questions, and evaluation findings."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. answer_sheet_uploads
    if "answer_sheet_uploads" in inspector.get_table_names():
        upload_cols = [c["name"] for c in inspector.get_columns("answer_sheet_uploads")]
        with op.batch_alter_table("answer_sheet_uploads", schema=None) as batch_op:
            if "total_pages" not in upload_cols:
                batch_op.add_column(sa.Column("total_pages", sa.Integer(), nullable=True, server_default=sa.text("0")))
            if "pages_completed" not in upload_cols:
                batch_op.add_column(sa.Column("pages_completed", sa.Integer(), nullable=True, server_default=sa.text("0")))
            batch_op.alter_column(
                "storage_path",
                existing_type=sa.VARCHAR(length=512),
                type_=sa.String(length=1024),
                existing_nullable=False,
            )

    # 2. questions
    if "questions" in inspector.get_table_names():
        q_cols = [c["name"] for c in inspector.get_columns("questions")]
        with op.batch_alter_table("questions", schema=None) as batch_op:
            if "is_reference_proposed" not in q_cols:
                batch_op.add_column(
                    sa.Column("is_reference_proposed", sa.Boolean(), nullable=False, server_default=sa.text("false"))
                )
            if "reference_status" not in q_cols:
                batch_op.add_column(
                    sa.Column("reference_status", sa.String(length=50), nullable=False, server_default=sa.text("'approved'"))
                )

    # 3. evaluation_findings
    if "evaluation_findings" in inspector.get_table_names():
        ef_cols = [c["name"] for c in inspector.get_columns("evaluation_findings")]
        with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
            if "verdict" not in ef_cols:
                batch_op.add_column(sa.Column("verdict", sa.String(length=50), nullable=True))
            if "correct_answer" not in ef_cols:
                batch_op.add_column(sa.Column("correct_answer", sa.Text(), nullable=True))
            if "marks_awarded" not in ef_cols:
                batch_op.add_column(sa.Column("marks_awarded", sa.Float(), nullable=True))
            if "max_marks" not in ef_cols:
                batch_op.add_column(sa.Column("max_marks", sa.Float(), nullable=True))
            if "marks_reason" not in ef_cols:
                batch_op.add_column(sa.Column("marks_reason", sa.Text(), nullable=True))
            if "error_amount" not in ef_cols:
                batch_op.add_column(sa.Column("error_amount", sa.String(length=100), nullable=True))
            if "error_type" not in ef_cols:
                batch_op.add_column(sa.Column("error_type", sa.String(length=100), nullable=True))
            if "step_by_step_explanation" not in ef_cols:
                batch_op.add_column(sa.Column("step_by_step_explanation", sa.Text(), nullable=True))
            if "misconception_hypothesis" not in ef_cols:
                batch_op.add_column(sa.Column("misconception_hypothesis", sa.Text(), nullable=True))
            if "remediation_concept" not in ef_cols:
                batch_op.add_column(sa.Column("remediation_concept", sa.String(length=255), nullable=True))
            if "follow_up_question" not in ef_cols:
                batch_op.add_column(sa.Column("follow_up_question", sa.Text(), nullable=True))

        # Create index on verdict if index doesn't already exist
        indices = [idx["name"] for idx in inspector.get_indexes("evaluation_findings")]
        if "ix_evaluation_findings_verdict" not in indices:
            op.create_index(
                op.f("ix_evaluation_findings_verdict"),
                "evaluation_findings",
                ["verdict"],
                unique=False,
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "questions" in inspector.get_table_names():
        with op.batch_alter_table("questions", schema=None) as batch_op:
            batch_op.drop_column("reference_status")
            batch_op.drop_column("is_reference_proposed")

    if "evaluation_findings" in inspector.get_table_names():
        indices = [idx["name"] for idx in inspector.get_indexes("evaluation_findings")]
        if "ix_evaluation_findings_verdict" in indices:
            op.drop_index(op.f("ix_evaluation_findings_verdict"), table_name="evaluation_findings")

        with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
            batch_op.drop_column("follow_up_question")
            batch_op.drop_column("remediation_concept")
            batch_op.drop_column("misconception_hypothesis")
            batch_op.drop_column("step_by_step_explanation")
            batch_op.drop_column("error_type")
            batch_op.drop_column("error_amount")
            batch_op.drop_column("marks_reason")
            batch_op.drop_column("max_marks")
            batch_op.drop_column("marks_awarded")
            batch_op.drop_column("correct_answer")
            batch_op.drop_column("verdict")

    if "answer_sheet_uploads" in inspector.get_table_names():
        with op.batch_alter_table("answer_sheet_uploads", schema=None) as batch_op:
            batch_op.alter_column(
                "storage_path",
                existing_type=sa.String(length=1024),
                type_=sa.VARCHAR(length=512),
                existing_nullable=False,
            )
            batch_op.drop_column("pages_completed")
            batch_op.drop_column("total_pages")
