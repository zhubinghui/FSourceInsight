"""Operator pause marker for crawl scheduling; expand-only.

Revision ID: c2e8a4f6b917
Revises: b9d4f6a2c813
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2e8a4f6b917'
down_revision = 'b9d4f6a2c813'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crawl_source_state') as batch:
        batch.add_column(sa.Column('paused_at', sa.DateTime(), nullable=True))


def downgrade():
    raise RuntimeError('Expand-only: keep operator pause markers')
