"""autonomy: grant modes (auto / heads-up / ask) with daily caps, heads-up requests, autonomy presets

Revision ID: f4c2d8a1b7e3
Revises: e2a1c7b9d410
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

from app.dbtypes import UTCDateTime

revision: str = 'f4c2d8a1b7e3'
down_revision: Union[str, Sequence[str], None] = 'e2a1c7b9d410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('permission_grants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mode', sa.String(length=20), server_default='auto', nullable=False))
        batch_op.add_column(sa.Column('daily_cap', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source', sa.String(length=20), nullable=True))
    with op.batch_alter_table('user_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_approve_at', UTCDateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('queued_call', JSON, nullable=True))
        batch_op.add_column(sa.Column('ran_at', UTCDateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_user_requests_auto_approve_at'), ['auto_approve_at'], unique=False)
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('autonomy_preset', sa.String(length=20), nullable=True))
    op.create_table(
        'autonomous_actions',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('campaign_id', sa.String(length=32), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('autonomous_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_autonomous_actions_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_autonomous_actions_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('autonomous_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_autonomous_actions_created_at'))
        batch_op.drop_index(batch_op.f('ix_autonomous_actions_campaign_id'))
    op.drop_table('autonomous_actions')
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('autonomy_preset')
    with op.batch_alter_table('user_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_requests_auto_approve_at'))
        batch_op.drop_column('ran_at')
        batch_op.drop_column('queued_call')
        batch_op.drop_column('auto_approve_at')
    with op.batch_alter_table('permission_grants', schema=None) as batch_op:
        batch_op.drop_column('source')
        batch_op.drop_column('daily_cap')
        batch_op.drop_column('mode')
