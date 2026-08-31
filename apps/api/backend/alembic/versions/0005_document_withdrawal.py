"""Where a document came from, and whether it is still there.

Revision ID: 0005_document_withdrawal
Revises: 0004_section_node_key

Nothing removed a `documents` row when its JSON left `output/`. A document that the
parser started refusing -- Phase 2 moved two acts editions to `output/_refused/` and
holds nine more in `_provisional/` -- kept its rows, its stale parse and its
"approved" badges in the portal forever, and a reviewer had no way to tell a current
document from an abandoned one.

`withdrawn_at` is a timestamp, not a delete. The annotations, findings and exported
evidence that point at the document are the audit trail for a legally binding corpus;
losing them to a conversion that was rerun with the wrong flag would be far worse than
showing a document marked withdrawn. It clears itself if the stem reappears.

`corpus_origin` is what makes reconciliation safe. `corpus_lane` looks like it would
do -- it does not: it is the Library's browse facet (Customs, Sales Tax, ...) and a
row's lane says nothing about which corpus root the file was synced from. Without the
origin, `sync_corpus.py --only rules` would compute "everything not in the rules
corpus" and withdraw all 80 acts documents.

Both nullable and unbackfilled. A row synced before this landed has no origin, and the
`skipped` fast path in `sync_validated_pair` already refuses to skip a row whose
`corpus_lane` is unset -- `corpus_origin` joins that condition, so the next sync fills
it in the same way. Until a row has one it is never a withdrawal candidate, which is
the safe direction.
"""

from alembic import op

revision = "0005_document_withdrawal"
down_revision = "0004_section_node_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS corpus_origin TEXT")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS withdrawn_at TEXT")
    # The Library filters on it on every page load, and it is highly selective.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_withdrawn "
        "ON documents (withdrawn_at) WHERE withdrawn_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_withdrawn")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS withdrawn_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS corpus_origin")
