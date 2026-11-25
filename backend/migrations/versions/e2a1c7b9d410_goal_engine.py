"""goal engine: how a goal gets hit, approaches, experiments, learnings; measured metrics

Revision ID: e2a1c7b9d410
Revises: aa31ff934f4f
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

revision: str = 'e2a1c7b9d410'
down_revision: Union[str, Sequence[str], None] = 'aa31ff934f4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approach', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verified', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
        batch_op.drop_column('verified')
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('approach')
