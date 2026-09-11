"""Append-only sampling fingerprints, never backfill complete learning history.

Revision ID: f2a67b904d31
Revises: c9e41a7b620f
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a67b904d31'
down_revision = 'c9e41a7b620f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crawl_source_profile', sa.Column('capture_generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('crawl_source_profile', sa.Column('capture_history_complete', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('crawl_capture_manifest',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('crawl_source_profile.id'), nullable=False),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id'), nullable=False),
        sa.Column('preview_report_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('document_hash', sa.String(64), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('preview_report_id'),
        sa.UniqueConstraint('profile_id', 'sequence', name='uq_capture_profile_sequence'))
    op.create_index('idx_capture_profile_id', 'crawl_capture_manifest', ['profile_id', 'id'])


def downgrade():
    raise RuntimeError('Expand-only migration; retain capture history during application rollback')
