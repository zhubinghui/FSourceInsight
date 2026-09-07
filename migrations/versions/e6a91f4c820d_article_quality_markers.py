"""Preserve new crawl quality markers without guessing legacy quality/language."""
from alembic import op
import sqlalchemy as sa

revision = 'e6a91f4c820d'
down_revision = 'd472ac9e6102'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('article', sa.Column('content_level', sa.String(20), nullable=True))
    op.add_column('article', sa.Column('source_language', sa.String(35), nullable=True))
    op.add_column('article', sa.Column('crawl_provenance', sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError('Expand-only migration; retain quality evidence during application rollback')
