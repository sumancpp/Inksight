"""add_acknowledged_uncertainty_and_audit_hardening

Revision ID: 74ff18316c0b
Revises: 226019028561
Create Date: 2026-11-08 23:11:42.753414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74ff18316c0b'
down_revision: Union[str, Sequence[str], None] = '226019028561'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with structured acknowledged_uncertainty flag and nullable audit references."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    audit_cols = [c["name"] for c in inspector.get_columns("finding_review_audits")]
    with op.batch_alter_table("finding_review_audits", schema=None) as batch_op:
        if "acknowledged_uncertainty" not in audit_cols:
            batch_op.add_column(
                sa.Column("acknowledged_uncertainty", sa.Boolean(), nullable=False, server_default="0")
            )
        batch_op.alter_column("reviewer_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("finding_id", existing_type=sa.Integer(), nullable=True)

    finding_cols = [c["name"] for c in inspector.get_columns("evaluation_findings")]
    with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
        if "acknowledged_uncertainty" not in finding_cols:
            batch_op.add_column(
                sa.Column("acknowledged_uncertainty", sa.Boolean(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    """Downgrade schema by dropping added columns."""
    with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
        batch_op.drop_column("acknowledged_uncertainty")

    with op.batch_alter_table("finding_review_audits", schema=None) as batch_op:
        batch_op.drop_column("acknowledged_uncertainty")
