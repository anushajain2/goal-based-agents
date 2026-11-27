"""model usage: one row per model call, for cost by task

Revision ID: c3f9a6d2e7b4
Revises: b8e4f1a2c9d3
Create Date: 2026-11-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.dbtypes import UTCDateTime

revision: str = 'c3f9a6d2e7b4'
down_revision: Union[str, Sequence[str], None] = 'b8e4f1a2c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'model_usage',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('org_id', sa.String(length=32), nullable=True),
        sa.Column('campaign_id', sa.String(length=32), nullable=True),
        sa.Column('task', sa.String(length=40), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
        sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
        sa.Column('web_searches', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('created_at', UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('model_usage', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_model_usage_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_model_usage_task'), ['task'], unique=False)
        batch_op.create_index(batch_op.f('ix_model_usage_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('model_usage')
