"""add_hashed_password_to_users

Revision ID: a15dcc263571
Revises: d6c760e82d63
Create Date: 2026-11-02 01:28:11.491028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a15dcc263571'
down_revision: Union[str, Sequence[str], None] = 'd6c760e82d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hashed_password', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text("PRAGMA foreign_keys=OFF;"))
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('hashed_password')
    conn.execute(sa.text("PRAGMA foreign_keys=ON;"))
