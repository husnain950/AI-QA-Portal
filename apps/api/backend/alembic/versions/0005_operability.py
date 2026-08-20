"""Worker heartbeat and backup audit records.

Revision ID: 0005_operability
Revises: 0004_occurrence_identity
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_operability"
down_revision = "0004_occurrence_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.Text(), primary_key=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("heartbeat_at", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text()),
        sa.Column("version", sa.Text()),
    )
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text()),
        sa.Column("manifest_sha256", sa.Text()),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_table("backup_runs")
    op.drop_table("worker_heartbeats")
