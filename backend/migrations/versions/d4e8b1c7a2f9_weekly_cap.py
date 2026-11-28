"""weekly spending limit for long-term goals

Revision ID: d4e8b1c7a2f9
Revises: c3f9a6d2e7b4
Create Date: 2026-11-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e8b1c7a2f9'
down_revision: Union[str, Sequence[str], None] = 'c3f9a6d2e7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('weekly_cap', sa.Numeric(precision=14, scale=6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('weekly_cap')
