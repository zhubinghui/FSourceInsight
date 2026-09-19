"""Learning failure quarantine and append-only safe retry decisions.

Revision ID: f8b64d2c901e
Revises: e1c73d9b502a
"""
from alembic import op
import sqlalchemy as sa

revision = 'f8b64d2c901e'
down_revision = 'e1c73d9b502a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('crawl_repair_session', sa.Column('cooldown_until', sa.DateTime(), nullable=True))
    op.add_column('crawl_repair_session', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    # This is a new quarantine from migration execution, NOT a fabricated end time.
    # Add a second so second-resolution UTC timestamps never shorten six hours.
    if op.get_bind().dialect.name == 'mysql':
        until = 'DATE_ADD(UTC_TIMESTAMP(), INTERVAL 21601 SECOND)'
    else:
        until = "datetime('now', '+21601 seconds')"
    op.execute(sa.text(f"UPDATE crawl_repair_session SET cooldown_until={until} "
                       "WHERE state IN ('blocked','exhausted','cancelled')"))
    op.create_table('crawl_repair_retry',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('crawl_repair_session.id'), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('after_round', sa.Integer(), nullable=False),
        sa.Column('requested_by_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('note', sa.String(300), nullable=False),
        sa.Column('document_hash', sa.String(64), nullable=False),
        sa.UniqueConstraint('session_id', 'number', name='uq_repair_retry_number'),
        sa.UniqueConstraint('session_id', 'after_round', name='uq_repair_retry_round'),
    )


def downgrade():
    raise RuntimeError('Expand-only: retain cooldown, retry audit, exposures and uncertain charges')
