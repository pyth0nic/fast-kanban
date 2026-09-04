"""Add task metadata, versioning, and outbox support.

Revision ID: 9ef17dce4a12
Revises: 6551b629493c
Create Date: 2026-09-04 11:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '9ef17dce4a12'
down_revision: Union[str, Sequence[str], None] = '6551b629493c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('task', sa.Column('workspace_id', sa.String(), nullable=False, server_default=''))
    op.add_column('task', sa.Column('assignee_id', sa.String(), nullable=True))
    op.add_column('task', sa.Column('priority', sa.String(), nullable=False, server_default='medium'))
    op.add_column('task', sa.Column('due_at', sa.DateTime(), nullable=True))
    op.add_column('task', sa.Column('labels', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('task', sa.Column('external_ref', sa.String(), nullable=True))
    op.add_column('task', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))

    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_assignee_id'), ['assignee_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_due_at'), ['due_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_priority'), ['priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_version'), ['version'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_workspace_id'), ['workspace_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_external_ref'), ['external_ref'], unique=False)

    op.create_table(
        'task_outbox_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('task_outbox_event', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_outbox_event_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_outbox_event_version'), ['version'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_outbox_event_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_outbox_event_status'), ['status'], unique=False)

    op.create_table(
        'task_idempotency_record',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('request_hash', sa.String(), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('task_idempotency_record', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_idempotency_record_scope'), ['scope'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_idempotency_record_key'), ['key'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_idempotency_record_request_hash'), ['request_hash'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('task_idempotency_record')
    op.drop_table('task_outbox_event')

    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_task_external_ref'))
        batch_op.drop_index(batch_op.f('ix_task_assignee_id'))
        batch_op.drop_index(batch_op.f('ix_task_due_at'))
        batch_op.drop_index(batch_op.f('ix_task_priority'))
        batch_op.drop_index(batch_op.f('ix_task_version'))

    op.drop_column('task', 'version')
    op.drop_column('task', 'external_ref')
    op.drop_column('task', 'labels')
    op.drop_column('task', 'due_at')
    op.drop_column('task', 'priority')
    op.drop_column('task', 'assignee_id')
    op.drop_column('task', 'workspace_id')
