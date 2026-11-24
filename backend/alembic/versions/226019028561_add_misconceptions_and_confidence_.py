"""add_misconceptions_and_confidence_details_to_evaluation_findings

Revision ID: 226019028561
Revises: 92fe2315e0e9
Create Date: 2026-11-07 22:47:50.187441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '226019028561'
down_revision: Union[str, Sequence[str], None] = '92fe2315e0e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with structured misconceptions, confidence details, and review gate."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = [c["name"] for c in inspector.get_columns("evaluation_findings")]

    with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
        if "misconceptions" not in existing_cols:
            batch_op.add_column(
                sa.Column("misconceptions", sa.JSON(), nullable=False, server_default="[]")
            )
        if "confidence_details" not in existing_cols:
            batch_op.add_column(
                sa.Column("confidence_details", sa.JSON(), nullable=True)
            )
        if "requires_teacher_review" not in existing_cols:
            batch_op.add_column(
                sa.Column("requires_teacher_review", sa.Boolean(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    """Downgrade schema by dropping the added columns."""
    with op.batch_alter_table("evaluation_findings", schema=None) as batch_op:
        batch_op.drop_column("requires_teacher_review")
        batch_op.drop_column("confidence_details")
        batch_op.drop_column("misconceptions")
