"""Add explicit learning sessions/attempts; no historical authorization.

Revision ID: c4e92f7a610b
Revises: a8d31c5e7902
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e92f7a610b'
down_revision = 'a8d31c5e7902'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('crawl_repair_session',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('news_source.id'), nullable=False),
        sa.Column('base_version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id'), nullable=False),
        sa.Column('capture_id', sa.Integer(), sa.ForeignKey('crawl_capture_manifest.id'), nullable=False, unique=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('protocol_version', sa.String(40), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('reason', sa.String(80)),
        sa.Column('rounds', sa.Integer(), nullable=False),
        sa.Column('max_rounds', sa.Integer(), nullable=False),
        sa.Column('cost_limit', sa.Numeric(18, 6), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('deadline_at', sa.DateTime(), nullable=False))
    op.create_index('idx_repair_source_state', 'crawl_repair_session', ['source_id', 'state'])
    op.create_table('crawl_repair_attempt',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('crawl_repair_session.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('exposure', sa.JSON(), nullable=False),
        sa.Column('prompt_hash', sa.String(64), nullable=False),
        sa.Column('recipe_hash', sa.String(64)),
        sa.Column('feedback', sa.JSON()),
        sa.Column('candidate_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('session_id', 'number', name='uq_repair_attempt_number'))
    with op.batch_alter_table('llm_reservation') as batch:
        batch.add_column(sa.Column('learning_attempt_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_reservation_learning_attempt', 'crawl_repair_attempt', ['learning_attempt_id'], ['id'])


def downgrade():
    raise RuntimeError('Expand-only: retain learning attempts, exposure history and budget accounting')
