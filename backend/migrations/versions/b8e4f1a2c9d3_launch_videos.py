"""launch videos made from a company's website

Revision ID: b8e4f1a2c9d3
Revises: a7d3e9c2f5b1
Create Date: 2026-11-27 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

from app.dbtypes import UTCDateTime

revision: str = 'b8e4f1a2c9d3'
down_revision: Union[str, Sequence[str], None] = 'a7d3e9c2f5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'launch_videos',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('org_id', sa.String(length=32), nullable=False),
        sa.Column('campaign_id', sa.String(length=32), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('step', sa.String(length=200), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('storyboard', JSON, nullable=True),
        sa.Column('share_copy', sa.Text(), nullable=False),
        sa.Column('seconds', sa.Float(), nullable=True),
        sa.Column('video', sa.LargeBinary(), nullable=True),
        sa.Column('poster', sa.LargeBinary(), nullable=True),
        sa.Column('deliverable_id', sa.String(length=32), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('locked_by', sa.String(length=100), nullable=True),
        sa.Column('locked_at', UTCDateTime(timezone=True), nullable=True),
        sa.Column('created_at', UTCDateTime(timezone=True), nullable=False),
        sa.Column('updated_at', UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deliverable_id'], ['deliverables.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('launch_videos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_launch_videos_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_launch_videos_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_launch_videos_status'), ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('launch_videos')
