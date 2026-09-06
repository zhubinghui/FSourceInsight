"""Add explicit LLM role/priority without rewriting existing task assignments.

Revision ID: d472ac9e6102
Revises: c821b4f7d901
"""
from alembic import op
import sqlalchemy as sa

revision = 'd472ac9e6102'
down_revision = 'c821b4f7d901'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('llm_config', sa.Column('role', sa.String(16), nullable=False, server_default='primary'))
    op.add_column('llm_config', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))


def downgrade():
    # Application rollback may keep these additive columns. Removing them would
    # lose administrator routing decisions; require explicit data migration.
    raise RuntimeError('Expand-only routing migration: keep role/priority on code rollback')
