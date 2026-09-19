"""Track controlled-learning history without retroactively certifying exposures.

Revision ID: d9b72a6e410c
Revises: c4e92f7a610b
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9b72a6e410c'
down_revision = 'c4e92f7a610b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crawl_repair_session') as batch:
        batch.add_column(sa.Column('history_sequence', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('input_hash', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_learning_session_history_sequence', ['history_sequence'])
    with op.batch_alter_table('crawl_repair_attempt') as batch:
        batch.add_column(sa.Column('exposure_sequence', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('exposure_hash', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_learning_exposure_sequence', ['exposure_sequence'])
    op.create_table('crawl_learning_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_generation', sa.Integer(), nullable=False),
        sa.Column('exposure_generation', sa.Integer(), nullable=False),
        sa.Column('history_complete', sa.Boolean(), nullable=False))
    op.execute(sa.text('''
        INSERT INTO crawl_learning_history (id,session_generation,exposure_generation,history_complete)
        SELECT 1, (SELECT COUNT(*) FROM crawl_repair_session), (SELECT COUNT(*) FROM crawl_repair_attempt),
            CASE WHEN EXISTS (SELECT 1 FROM crawl_repair_session)
                   OR EXISTS (SELECT 1 FROM crawl_repair_attempt)
                   OR EXISTS (SELECT 1 FROM llm_reservation WHERE task_type='crawl_schema')
                   OR EXISTS (SELECT 1 FROM llm_usage_log WHERE task_type='crawl_schema')
                 THEN 0 ELSE 1 END
    '''))


def downgrade():
    raise RuntimeError('Expand-only: retain learning history, exposure fingerprints and budget accounting')
