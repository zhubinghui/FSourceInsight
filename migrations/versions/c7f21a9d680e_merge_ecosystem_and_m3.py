"""Join the released ecosystem review and M3 accounting/learning histories.

Revision ID: c7f21a9d680e
Revises: b3d5e8a1c407, b5d81e6a430f
"""
revision = 'c7f21a9d680e'
down_revision = ('b3d5e8a1c407', 'b5d81e6a430f')
branch_labels = None
depends_on = None


def upgrade():
    # Both additive branches are retained. No data rewrite or certification.
    pass


def downgrade():
    raise RuntimeError('Expand-only: retain ecosystem review and M3 accounting histories')
