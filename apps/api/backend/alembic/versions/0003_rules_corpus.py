"""A document count for the Rules corpus.

Revision ID: 0003_rules_corpus
Revises: 0002_auth

`corpus_sync_state` is a singleton row with one count column per corpus, so a third
corpus needs a third column. Guarded with IF NOT EXISTS for the same reason 0002 is:
on a fresh database the baseline has already built the table from
`db_schema.metadata`, which declares the column.

Nullable with a server default and no backfill -- the row is rewritten in full by the
next sync, so a NULL here means "not synced since this landed", which is true.
"""

from alembic import op

revision = "0003_rules_corpus"
down_revision = "0002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE corpus_sync_state "
        "ADD COLUMN IF NOT EXISTS rules_docs INTEGER DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE corpus_sync_state DROP COLUMN IF EXISTS rules_docs")
