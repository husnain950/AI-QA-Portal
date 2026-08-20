"""Store sanitizer change diagnostics.

Revision ID: 0003_sanitizer_diagnostics
Revises: 0002_review_invariants
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_sanitizer_diagnostics"
down_revision = "0002_review_invariants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("sections", "footnotes"):
        op.add_column(
            table,
            sa.Column(
                "sanitizer_diagnostics",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    for table in ("footnotes", "sections"):
        op.drop_column(table, "sanitizer_diagnostics")
