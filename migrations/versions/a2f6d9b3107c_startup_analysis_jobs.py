"""Add source-owned initial analysis intents, never retroactive ownership.

Revision ID: a2f6d9b3107c
Revises: f8b64d2c901e
"""
from alembic import op
import sqlalchemy as sa

revision = 'a2f6d9b3107c'
down_revision = 'f8b64d2c901e'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('company', 'startup_source'):
        op.add_column(table, sa.Column('analysis_generation', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('startup_analysis_job',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('company.id', ondelete='SET NULL'), unique=True),
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('startup_source.id', ondelete='SET NULL')),
        sa.Column('protocol', sa.String(40), nullable=False),
        sa.Column('inputs', sa.JSON(), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('prompt_hash', sa.String(64), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(80)),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('deadline_at', sa.DateTime()),
        sa.Column('next_dispatch_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime()))
    op.create_index('idx_startup_analysis_pending', 'startup_analysis_job', ['state', 'next_dispatch_at'])
    op.create_index('idx_startup_analysis_source', 'startup_analysis_job', ['source_id', 'created_at'])
    with op.batch_alter_table('llm_reservation') as batch:
        batch.add_column(sa.Column('startup_analysis_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_reservation_startup_analysis', 'startup_analysis_job', ['startup_analysis_id'], ['id'])
        batch.create_index('ix_llm_reservation_startup_analysis_id', ['startup_analysis_id'])


def downgrade():
    raise RuntimeError('Expand-only: retain discovery ownership, execution records and uncertain charges')
