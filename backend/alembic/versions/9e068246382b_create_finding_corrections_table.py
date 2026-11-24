"""create_finding_corrections_table

Revision ID: 9e068246382b
Revises: bf2db0d5e04a
Create Date: 2026-11-09 00:02:47.065263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e068246382b'
down_revision: Union[str, Sequence[str], None] = 'bf2db0d5e04a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "finding_corrections" not in tables:
        op.create_table(
            "finding_corrections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("finding_id", sa.Integer(), sa.ForeignKey("evaluation_findings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field_name", sa.String(length=50), nullable=False),
            sa.Column("original_value", sa.JSON(), nullable=True),
            sa.Column("corrected_value", sa.JSON(), nullable=False),
            sa.Column("corrected_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("corrected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("correction_reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        )
        op.create_index(op.f("ix_finding_corrections_id"), "finding_corrections", ["id"], unique=False)
        op.create_index(op.f("ix_finding_corrections_finding_id"), "finding_corrections", ["finding_id"], unique=False)
        op.create_index(op.f("ix_finding_corrections_field_name"), "finding_corrections", ["field_name"], unique=False)
        op.create_index(op.f("ix_finding_corrections_corrected_by"), "finding_corrections", ["corrected_by"], unique=False)
        op.create_index(op.f("ix_finding_corrections_status"), "finding_corrections", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    if "finding_corrections" in tables:
        op.drop_index(op.f("ix_finding_corrections_status"), table_name="finding_corrections")
        op.drop_index(op.f("ix_finding_corrections_corrected_by"), table_name="finding_corrections")
        op.drop_index(op.f("ix_finding_corrections_field_name"), table_name="finding_corrections")
        op.drop_index(op.f("ix_finding_corrections_finding_id"), table_name="finding_corrections")
        op.drop_index(op.f("ix_finding_corrections_id"), table_name="finding_corrections")
        op.drop_table("finding_corrections")
