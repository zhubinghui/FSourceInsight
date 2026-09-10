"""Add immutable source policy decisions without granting legacy sources access."""
from alembic import op
import sqlalchemy as sa

revision = 'c9e41a7b620f'
down_revision = 'b6c2a4d9e710'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crawl_source_profile', sa.Column('source_generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('crawl_source_profile', sa.Column('policy_generation', sa.Integer(), nullable=True))
    op.create_table(
        'crawl_policy_version',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('crawl_source_profile.id'), nullable=False),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('source_generation', sa.Integer(), nullable=False),
        sa.Column('source_fingerprint', sa.String(64), nullable=False),
        sa.Column('document', sa.JSON(), nullable=False),
        sa.Column('document_hash', sa.String(64), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('profile_id', 'generation', name='uq_policy_profile_generation'),
    )
    op.create_index('idx_policy_profile_id', 'crawl_policy_version', ['profile_id', 'id'])


def downgrade():
    raise RuntimeError('Expand-only migration; retain policy history during application rollback')
