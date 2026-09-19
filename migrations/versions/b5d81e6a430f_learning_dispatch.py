"""Bound learning redispatch; preserve legacy intents without enabling them.

Revision ID: b5d81e6a430f
Revises: a2f6d9b3107c
"""
from alembic import op
import sqlalchemy as sa

revision = 'b5d81e6a430f'
down_revision = 'a2f6d9b3107c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crawl_repair_session', sa.Column('dispatch_due_at', sa.DateTime(), nullable=True))
    op.create_index('idx_repair_dispatch_due', 'crawl_repair_session', ['state', 'dispatch_due_at'])


def downgrade():
    raise RuntimeError('Expand-only: retain learning dispatch state, history and uncertain charges')
