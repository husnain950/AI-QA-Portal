"""Flatten compilation instrument context onto review leaves.

Revision ID: 0006_section_instrument_context
Revises: 0005_document_withdrawal

The pipeline contract may now place chapter/schedule trees under
``instruments[]``. These nullable columns preserve the containing instrument's
stable legal code and display heading on every flattened section. Legacy
documents remain NULL.

Guarded with IF NOT EXISTS because the PostgreSQL baseline creates tables from
``db_schema.metadata`` and therefore already includes these columns on a fresh
database.
"""

from alembic import op

revision = "0006_section_instrument_context"
down_revision = "0005_document_withdrawal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS instrument_code TEXT")
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS instrument_heading TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE sections DROP COLUMN IF EXISTS instrument_heading")
    op.execute("ALTER TABLE sections DROP COLUMN IF EXISTS instrument_code")
