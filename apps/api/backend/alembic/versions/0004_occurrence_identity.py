"""Constrain stable leaf source identities.

Revision ID: 0004_occurrence_identity
Revises: 0003_sanitizer_diagnostics
"""

from alembic import op

revision = "0004_occurrence_identity"
down_revision = "0003_sanitizer_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_leaf_occurrence_source
        ON leaf_occurrences (document_id, source_key)
        WHERE source_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("uq_leaf_occurrence_source", table_name="leaf_occurrences")
