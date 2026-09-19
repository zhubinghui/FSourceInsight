"""Freeze learning candidates and retain bounded holdout reports.

Revision ID: e1c73d9b502a
Revises: d9b72a6e410c
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1c73d9b502a'
down_revision = 'd9b72a6e410c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crawl_learning_history') as batch:
        batch.add_column(sa.Column('selection_generation', sa.Integer(), nullable=False, server_default='0'))
    op.create_table('crawl_validation_report',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('capture_id', sa.Integer()),
        sa.Column('binding', sa.JSON(), nullable=False),
        sa.Column('binding_hash', sa.String(64), nullable=False),
        sa.Column('selection', sa.JSON()), sa.Column('selection_hash', sa.String(64)),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('result', sa.JSON()), sa.Column('result_hash', sa.String(64)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('requested_by_id', sa.Integer()), sa.Column('deadline_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['session_id'], ['crawl_repair_session.id']),
        sa.ForeignKeyConstraint(['candidate_id'], ['crawl_schema_version.id']),
        sa.ForeignKeyConstraint(['capture_id'], ['crawl_capture_manifest.id']),
        sa.ForeignKeyConstraint(['requested_by_id'], ['user.id']),
        sa.UniqueConstraint('session_id', name='uq_validation_session'),
        sa.UniqueConstraint('candidate_id', name='uq_validation_candidate'))
    op.create_index('idx_validation_state_deadline', 'crawl_validation_report', ['state', 'deadline_at'])


def downgrade():
    raise RuntimeError('Expand-only: retain validation selection and result history')
