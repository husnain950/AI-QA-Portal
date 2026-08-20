"""Add exact variant evidence and orphaned-finding state.

Revision ID: 0002_review_invariants
Revises: 0001_postgres_baseline
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_review_invariants"
down_revision = "0001_postgres_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "section_variants",
        sa.Column("html_sha", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "findings",
        sa.Column("orphaned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("findings", "orphaned")
    op.drop_column("section_variants", "html_sha")
