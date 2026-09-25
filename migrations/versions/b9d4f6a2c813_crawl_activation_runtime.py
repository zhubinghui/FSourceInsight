"""Crawl activation pointers, run claims and the article LLM outbox; expand-only, no backfill.

Revision ID: b9d4f6a2c813
Revises: d3e7a1c95b28
"""
from alembic import op
import sqlalchemy as sa

revision = 'b9d4f6a2c813'
down_revision = 'd3e7a1c95b28'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crawl_source_profile') as batch:
        batch.add_column(sa.Column('active_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('previous_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('activation_generation', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('active_source_generation', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_profile_active_version', 'crawl_schema_version', ['active_version_id'], ['id'])
        batch.create_foreign_key('fk_profile_previous_version', 'crawl_schema_version', ['previous_version_id'], ['id'])
    with op.batch_alter_table('crawl_log') as batch:
        batch.add_column(sa.Column('claim_id', sa.String(36), nullable=True))
        batch.add_column(sa.Column('fence', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('route', sa.String(16), nullable=True))
        batch.add_column(sa.Column('activation_generation', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('schema_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('policy_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('outcome', sa.String(24), nullable=True))
        batch.add_column(sa.Column('error_code', sa.String(40), nullable=True))
        batch.create_foreign_key('fk_crawl_log_schema_version', 'crawl_schema_version', ['schema_version_id'], ['id'])
        batch.create_foreign_key('fk_crawl_log_policy_version', 'crawl_policy_version', ['policy_version_id'], ['id'])
    op.create_table('crawl_schema_decision',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('crawl_source_profile.id'), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id')),
        sa.Column('from_version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id')),
        sa.Column('activation_generation', sa.Integer(), nullable=False),
        sa.Column('evidence_kind', sa.String(16)),
        sa.Column('evidence_ref', sa.String(64)),
        sa.Column('evidence_hash', sa.String(64)),
        sa.Column('source_generation', sa.Integer(), nullable=False),
        sa.Column('policy_version_id', sa.Integer(), sa.ForeignKey('crawl_policy_version.id')),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('reason', sa.String(200)),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('idx_schema_decision_profile', 'crawl_schema_decision', ['profile_id', 'id'])
    op.create_table('crawl_source_state',
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('news_source.id'), primary_key=True),
        sa.Column('next_due_at', sa.DateTime(), nullable=False),
        sa.Column('due_reason', sa.String(16), nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attention_reason', sa.String(40)),
        sa.Column('attention_since', sa.DateTime()),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('lease_expires_at', sa.DateTime()),
        sa.Column('fence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('running_log_id', sa.Integer(), sa.ForeignKey('crawl_log.id')))
    op.create_index('idx_crawl_state_due', 'crawl_source_state', ['next_due_at'])
    op.create_table('article_llm_job',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('article.id', ondelete='SET NULL')),
        sa.Column('active_article_id', sa.Integer(), sa.ForeignKey('article.id', ondelete='SET NULL'), unique=True),
        sa.Column('trigger', sa.String(16), nullable=False),
        sa.Column('crawl_log_id', sa.Integer(), sa.ForeignKey('crawl_log.id')),
        sa.Column('force', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(80)),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('deadline_at', sa.DateTime()),
        sa.Column('next_dispatch_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime()))
    op.create_index('ix_article_llm_job_article_id', 'article_llm_job', ['article_id'])
    op.create_index('idx_article_llm_job_pending', 'article_llm_job', ['state', 'next_dispatch_at'])


def downgrade():
    raise RuntimeError('Expand-only: retain activation decisions, run history and article LLM jobs')
