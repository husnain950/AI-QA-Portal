"""The pipeline's structural identity for a leaf.

Revision ID: 0004_section_node_key
Revises: 0003_rules_corpus

`sections.source_key` is the positional JSON-pointer path the flattener mints
(`/chapters/0/sections/3`), so inserting one leaf renames every later sibling.
Measured over the corpus, one inserted leaf per document reported **386 leaves as
"changed"** that had not changed, and 16 documents churned 100% of themselves --
which in `apply_parsed_document` resets approvals and re-anchors annotations against
the wrong leaf's text.

`node_key` is the pipeline's ancestor-chain-by-code (`ch:vii/pt:i/s:114`). It has
been emitted since PR #42 and consumed by nothing.

Nullable and unbackfilled on purpose. Existing rows keep their ids; the first sync
after this lands matches them by `source_key` exactly as before and fills `node_key`
in as it goes, so nothing is re-minted and no id in an exported evidence bundle
changes. Documents converted before `contract_version` 1 have no `node_key` at all
and keep matching by `source_key` -- that fallback is the contract's only
backwards-compatibility affordance and is deleted once nothing relies on it.

Guarded with IF NOT EXISTS for the same reason 0002 and 0003 are: on a fresh
database the baseline has already built the table from `db_schema.metadata`, which
declares the column.
"""

from alembic import op

revision = "0004_section_node_key"
down_revision = "0003_rules_corpus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS node_key TEXT")
    # Unique for the same reason the `source_key` index is: a duplicate would merge
    # two leaves' review state silently. Partial, so the pre-contract rows that have
    # no key do not collide with each other on NULL.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sections_node_key "
        "ON sections (document_id, node_key) WHERE node_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sections_node_key")
    op.execute("ALTER TABLE sections DROP COLUMN IF EXISTS node_key")
