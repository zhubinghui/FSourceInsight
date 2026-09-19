"""Ecosystem review state and verified location; existing rows stay approved.

Revision ID: b3d5e8a1c407
Revises: f2a67b904d31
"""
from alembic import op
import sqlalchemy as sa

revision = 'b3d5e8a1c407'
down_revision = 'f2a67b904d31'
branch_labels = None
depends_on = None


def upgrade():
    # Server defaults keep legacy rows and old-application inserts visible.
    op.add_column('company', sa.Column('review_status', sa.String(20), nullable=False, server_default='approved'))
    op.add_column('company', sa.Column('entity_type', sa.String(30)))
    op.add_column('company', sa.Column('postcode', sa.String(10)))
    op.add_column('company', sa.Column('city', sa.String(120)))
    op.add_column('company', sa.Column('local_site', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    raise RuntimeError('Expand-only migration; retain review decisions during application rollback')
