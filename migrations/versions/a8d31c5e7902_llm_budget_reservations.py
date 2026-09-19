"""Add conservative billable-attempt reservations; do not certify old configs.

Revision ID: a8d31c5e7902
Revises: f2a67b904d31
"""
from alembic import op
import sqlalchemy as sa

revision = 'a8d31c5e7902'
down_revision = 'f2a67b904d31'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('llm_config', sa.Column('billing_input_limit', sa.Integer(), nullable=True))
    op.add_column('llm_config', sa.Column('billing_output_limit', sa.Integer(), nullable=True))
    op.create_table('llm_budget_gate', sa.Column('id', sa.Integer(), primary_key=True))
    op.create_table('llm_reservation',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('config_id', sa.Integer(), sa.ForeignKey('llm_config.id'), nullable=False),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('billing_day', sa.Date(), nullable=False),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('model', sa.String(200), nullable=False),
        sa.Column('endpoint_hash', sa.String(64), nullable=False),
        sa.Column('input_limit', sa.Integer(), nullable=False),
        sa.Column('output_limit', sa.Integer(), nullable=False),
        sa.Column('input_price', sa.Numeric(10, 6), nullable=False),
        sa.Column('output_price', sa.Numeric(10, 6), nullable=False),
        sa.Column('reserved_usd', sa.Numeric(18, 6), nullable=False),
        sa.Column('actual_usd', sa.Numeric(18, 6)),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('usage_id', sa.Integer(), sa.ForeignKey('llm_usage_log.id'), unique=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('settled_at', sa.DateTime()))
    op.create_index('idx_llm_reservation_day_state', 'llm_reservation', ['billing_day', 'state'])
    op.create_table('llm_reconciliation',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reservation_id', sa.String(36), sa.ForeignKey('llm_reservation.id'), nullable=False, unique=True),
        sa.Column('final_cost', sa.Numeric(18, 6), nullable=False),
        sa.Column('evidence_note', sa.String(500), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))


def downgrade():
    raise RuntimeError('Expand-only: retain budget accounting and pending reservations; do not downgrade')
