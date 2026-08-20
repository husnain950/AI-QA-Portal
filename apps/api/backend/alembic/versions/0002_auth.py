"""Local accounts, roles, and server-side sessions.

Revision ID: 0002_auth
Revises: 0001_postgres_baseline

Guarded with IF NOT EXISTS because the baseline builds the schema from the live
db_schema.metadata, which already declares these tables: on a fresh database
create_all has made them before this revision runs.
"""

from alembic import op

revision = "0002_auth"
down_revision = "0001_postgres_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'reader',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            CONSTRAINT ck_users_role CHECK (role IN ('reader','reviewer','admin'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            token_sha TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            user_agent TEXT,
            client_ip TEXT
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_sessions")
    op.execute("DROP TABLE IF EXISTS users")
