"""Persist bounded admin previews, not raw pages or publication authority."""
from alembic import op
import sqlalchemy as sa

revision = 'b6c2a4d9e710'
down_revision = 'a731c9e25d80'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'crawl_preview_report',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id'), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('source_fingerprint', sa.String(64), nullable=False),
        sa.Column('recipe_hash', sa.String(64), nullable=False),
        sa.Column('engine_version', sa.String(40), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('report', sa.JSON(), nullable=False),
    )
    op.create_index('idx_preview_version_id', 'crawl_preview_report', ['version_id', 'id'])


def downgrade():
    raise RuntimeError('Expand-only migration; retain preview history during application rollback')
