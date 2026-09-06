"""Widen usage task_type to match the model without dropping usage history.

Revision ID: c821b4f7d901
Revises: fd3132082a6b

This is an expand-only migration. Older application code already models this
column as String(50), so code rollback does not require narrowing the column.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c821b4f7d901'
down_revision = 'fd3132082a6b'
branch_labels = None
depends_on = None


def upgrade():
    # Some deployed databases already have the model's VARCHAR column even
    # though their migration history is at the previous revision. Avoid a
    # needless table ALTER/metadata lock on a large paid-usage ledger.
    if not op.get_context().as_sql:
        column = next(c for c in sa.inspect(op.get_bind()).get_columns('llm_usage_log')
                      if c['name'] == 'task_type')
        if (isinstance(column['type'], sa.String)
                and not isinstance(column['type'], sa.Enum)
                and column['type'].length == 50 and not column['nullable']):
            return
    op.alter_column(
        'llm_usage_log', 'task_type',
        existing_type=sa.Enum('translate', 'summarize', 'ner', 'sentiment', 'classify',
                              name='llm_task_type_enum'),
        type_=sa.String(50), existing_nullable=False,
    )


def downgrade():
    # Casting digest/insight/company_analysis back to the old Enum would lose
    # paid usage evidence (or fail in strict MySQL). Refuse rather than truncate.
    raise RuntimeError('Expand-only migration: keep VARCHAR(50) during code rollback; narrowing requires an explicit data migration.')
