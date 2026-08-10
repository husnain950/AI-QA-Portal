import os

import aiosqlite

from backend.migrations import run_migrations
from backend.migrations.m0001_initial import upgrade as ensure_schema

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB_DIR = os.path.join(_BACKEND_DIR, "data")

# Prefer env so Docker / Makefile can point at data/db without editing code.
DB_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(_DEFAULT_DB_DIR, "qa_portal.db"),
)
DB_DIR = os.path.dirname(os.path.abspath(DB_PATH))


async def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("PRAGMA cache_size = 500;")
        await db.execute("PRAGMA temp_store = FILE;")
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    """Create/upgrade schema via versioned migrations, then re-ensure idempotent bits."""
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("PRAGMA cache_size = 500;")
        await db.execute("PRAGMA temp_store = FILE;")
        await run_migrations(db)
        # Migrations are skipped once applied; re-run the idempotent upgrade so FTS
        # stays in sync and any CREATE IF NOT EXISTS safety nets still fire on boot.
        await ensure_schema(db)
