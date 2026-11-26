"""desktop helper: paired computers, pairing codes, screenshots in the database

Revision ID: f3b8d2c61a07
Revises: e2a1c7b9d410
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.dbtypes import UTCDateTime

revision: str = 'f3b8d2c61a07'
down_revision: Union[str, Sequence[str], None] = 'e2a1c7b9d410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'helper_devices',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('org_id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('platform', sa.String(length=40), nullable=True),
        sa.Column('app_version', sa.String(length=40), nullable=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('paused', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', UTCDateTime(), nullable=False),
        sa.Column('last_seen_at', UTCDateTime(), nullable=True),
        sa.Column('revoked_at', UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_helper_devices_org_id_organizations', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_helper_devices_user_id_users', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name='pk_helper_devices'),
        sa.UniqueConstraint('token_hash', name='uq_helper_devices_token_hash'),
    )
    op.create_index('ix_helper_devices_org_id', 'helper_devices', ['org_id'])
    op.create_table(
        'helper_pairings',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('org_id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', UTCDateTime(), nullable=False),
        sa.Column('used_at', UTCDateTime(), nullable=True),
        sa.Column('created_at', UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_helper_pairings_org_id_organizations', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_helper_pairings_user_id_users', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name='pk_helper_pairings'),
        sa.UniqueConstraint('code_hash', name='uq_helper_pairings_code_hash'),
    )
    op.create_index('ix_helper_pairings_org_id', 'helper_pairings', ['org_id'])
    op.create_table(
        'screenshots',
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('name', name='pk_screenshots'),
    )
    op.create_index('ix_screenshots_created_at', 'screenshots', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_screenshots_created_at', table_name='screenshots')
    op.drop_table('screenshots')
    op.drop_index('ix_helper_pairings_org_id', table_name='helper_pairings')
    op.drop_table('helper_pairings')
    op.drop_index('ix_helper_devices_org_id', table_name='helper_devices')
    op.drop_table('helper_devices')
