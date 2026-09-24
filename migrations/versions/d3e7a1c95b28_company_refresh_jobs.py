"""Add durable refresh intents for already-analysed companies; no backfill.

Revision ID: d3e7a1c95b28
Revises: c7f21a9d680e
"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e7a1c95b28'
down_revision = 'c7f21a9d680e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('company_refresh_job',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('company.id', ondelete='SET NULL')),
        sa.Column('active_company_id', sa.Integer(), sa.ForeignKey('company.id', ondelete='SET NULL'), unique=True),
        sa.Column('trigger', sa.String(16), nullable=False),
        sa.Column('trigger_ref', sa.String(80)),
        sa.Column('protocol', sa.String(40), nullable=False),
        sa.Column('company_generation', sa.Integer()),
        sa.Column('prompt_hash', sa.String(64)),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(80)),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('deadline_at', sa.DateTime()),
        sa.Column('next_dispatch_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime()))
    op.create_index('ix_company_refresh_job_company_id', 'company_refresh_job', ['company_id'])
    op.create_index('idx_company_refresh_pending', 'company_refresh_job', ['state', 'next_dispatch_at'])
    with op.batch_alter_table('llm_reservation') as batch:
        batch.add_column(sa.Column('company_refresh_id', sa.String(36), nullable=True))
        batch.create_foreign_key('fk_reservation_company_refresh', 'company_refresh_job', ['company_refresh_id'], ['id'])
        batch.create_index('ix_llm_reservation_company_refresh_id', ['company_refresh_id'])


def downgrade():
    raise RuntimeError('Expand-only: retain refresh execution records and uncertain charges')
