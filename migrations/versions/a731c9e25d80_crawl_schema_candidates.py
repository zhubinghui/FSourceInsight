"""Add isolated crawl candidates; never enable or rewrite existing sources."""
from alembic import op
import sqlalchemy as sa

revision = 'a731c9e25d80'
down_revision = 'e6a91f4c820d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'crawl_source_profile',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('news_source.id'), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.UniqueConstraint('source_id', name='uq_crawl_profile_source'),
    )
    op.create_table(
        'crawl_schema_version',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('crawl_source_profile.id'), nullable=False),
        sa.Column('recipe', sa.JSON(), nullable=False),
        sa.Column('recipe_hash', sa.String(64), nullable=False),
        sa.Column('base_generation', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('idx_schema_profile_id', 'crawl_schema_version', ['profile_id', 'id'])


def downgrade():
    raise RuntimeError('Expand-only migration; retain candidate history during application rollback')
