"""The migrated database must match db_schema, and must be reversible.

This replaces two tests that built a legacy SQLite file and read ``PRAGMA table_info``.
The invariant they protected — the schema the code expects is the schema migrations
produce — is what is checked here, against the database the application actually uses.
"""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

import backend.database as database
import backend.db_schema as db_schema

# Indexes and triggers 0001 creates with raw DDL, so metadata cannot describe them.
_RAW_DDL_INDEXES = {"idx_sections_search"}


def test_migrated_schema_matches_db_schema(test_database_url):
    """Every table and column the code declares exists in the migrated database."""
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        live_tables = set(inspector.get_table_names())
        for table in db_schema.metadata.sorted_tables:
            assert table.name in live_tables, f"{table.name} is missing from the database"
            live_columns = {column["name"] for column in inspector.get_columns(table.name)}
            declared = {column.name for column in table.columns}
            assert declared <= live_columns, (
                f"{table.name} is missing {sorted(declared - live_columns)}"
            )
    finally:
        engine.dispose()


def test_the_source_columns_and_indexes_the_review_code_relies_on(test_database_url):
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        documents = {column["name"] for column in inspector.get_columns("documents")}
        sections = {column["name"] for column in inspector.get_columns("sections")}
        section_indexes = {index["name"] for index in inspector.get_indexes("sections")}
    finally:
        engine.dispose()

    assert {
        "source_type",
        "source_key",
        "source_hash",
        "provenance",
        "corpus_lane",
        "statute_family_id",
    } <= documents
    assert {"source_key", "quality_flags", "hierarchy_kind", "reviewer_verdict"} <= sections
    # A unique partial index now, so one document cannot hold two rows for a source key.
    assert "uq_sections_source" in section_indexes
    assert _RAW_DDL_INDEXES <= section_indexes, "the full-text GIN index must exist"


@pytest.mark.usefixtures("test_database_url")
def test_downgrade_and_upgrade_round_trip():
    """`alembic downgrade base` must leave a database the baseline can rebuild."""
    config = database._alembic_config()
    command.downgrade(config, "base")
    engine = create_engine(database.normalize_database_url(config.get_main_option("sqlalchemy.url")))
    try:
        assert "documents" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(database.normalize_database_url(config.get_main_option("sqlalchemy.url")))
    try:
        assert "documents" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
