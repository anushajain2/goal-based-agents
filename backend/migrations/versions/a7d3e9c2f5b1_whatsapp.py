"""whatsapp: connected numbers, 24-hour window, conversation state, message log

Revision ID: a7d3e9c2f5b1
Revises: f3b8d2c61a07
Create Date: 2026-11-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql

from app.dbtypes import UTCDateTime

revision: str = 'a7d3e9c2f5b1'
down_revision: Union[str, Sequence[str], None] = 'f3b8d2c61a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('whatsapp_number', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('whatsapp_linked_at', UTCDateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('whatsapp_last_inbound_at', UTCDateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('whatsapp_prefs', JSON, nullable=True))
        batch_op.add_column(sa.Column('whatsapp_state', JSON, nullable=True))
        batch_op.add_column(sa.Column('whatsapp_link_code_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('whatsapp_link_code_expires_at', UTCDateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint('uq_users_whatsapp_number', ['whatsapp_number'])
        batch_op.create_index(batch_op.f('ix_users_whatsapp_link_code_hash'), ['whatsapp_link_code_hash'], unique=False)
    op.create_table(
        'whatsapp_messages',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=True),
        sa.Column('request_id', sa.String(length=32), nullable=True),
        sa.Column('wa_message_id', sa.String(length=200), nullable=False),
        sa.Column('direction', sa.String(length=3), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('created_at', UTCDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('whatsapp_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_request_id'), ['request_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_wa_message_id'), ['wa_message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_whatsapp_messages_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('whatsapp_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_created_at'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_wa_message_id'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_request_id'))
        batch_op.drop_index(batch_op.f('ix_whatsapp_messages_user_id'))
    op.drop_table('whatsapp_messages')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_whatsapp_link_code_hash'))
        batch_op.drop_constraint('uq_users_whatsapp_number', type_='unique')
        batch_op.drop_column('whatsapp_link_code_expires_at')
        batch_op.drop_column('whatsapp_link_code_hash')
        batch_op.drop_column('whatsapp_state')
        batch_op.drop_column('whatsapp_prefs')
        batch_op.drop_column('whatsapp_last_inbound_at')
        batch_op.drop_column('whatsapp_linked_at')
        batch_op.drop_column('whatsapp_number')
