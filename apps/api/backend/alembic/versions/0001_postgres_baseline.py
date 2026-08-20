"""Create the PostgreSQL production schema.

The single baseline: it builds the schema from ``db_schema.metadata``, which is the
live definition, so a follow-up revision must never re-add a column that metadata
already declares — on a fresh database create_all() has already made it.  Additive
revisions therefore go in metadata *and* in a revision guarded by IF NOT EXISTS.

Revision ID: 0001_postgres_baseline
Revises:
"""

from alembic import op

from backend.db_schema import metadata

revision = "0001_postgres_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), checkfirst=True)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sections_search ON sections USING gin (
            to_tsvector(
                'simple',
                coalesce(section_code, '') || ' ' ||
                coalesce(section_heading, '') || ' ' ||
                coalesce(plain_text, '')
            )
        )
        """
    )
    op.execute("INSERT INTO corpus_sync_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_review_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'review_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER review_events_no_update BEFORE UPDATE ON review_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_review_event_mutation()"
    )
    op.execute(
        "CREATE TRIGGER review_events_no_delete BEFORE DELETE ON review_events "
        "FOR EACH ROW EXECUTE FUNCTION reject_review_event_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS reject_review_event_mutation() CASCADE")
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
