"""Versioned schema migrations for the QA portal SQLite database.

Each migration module exposes ``version`` (int) and ``upgrade(db)`` (async).
``run_migrations`` applies pending versions in order and records them in
``schema_version``. Boot remains idempotent: CREATE IF NOT EXISTS + guarded ALTERs.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Awaitable, Callable, List, Tuple

import aiosqlite

MigrationFn = Callable[[aiosqlite.Connection], Awaitable[None]]


def _discover() -> List[Tuple[int, MigrationFn]]:
    package = importlib.import_module("backend.migrations")
    found: List[Tuple[int, MigrationFn]] = []
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        name = module_info.name.rsplit(".", 1)[-1]
        if not name.startswith("m"):
            continue
        module = importlib.import_module(module_info.name)
        version = getattr(module, "VERSION", None)
        upgrade = getattr(module, "upgrade", None)
        if isinstance(version, int) and callable(upgrade):
            found.append((version, upgrade))
    found.sort(key=lambda item: item[0])
    return found


async def _ensure_schema_version_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    await db.commit()


async def current_version(db: aiosqlite.Connection) -> int:
    await _ensure_schema_version_table(db)
    async with db.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version;") as cur:
        row = await cur.fetchone()
    return int(row[0] if row else 0)


async def run_migrations(db: aiosqlite.Connection) -> int:
    """Apply all pending migrations. Returns the latest applied version."""
    await _ensure_schema_version_table(db)
    applied = await current_version(db)
    latest = applied
    for version, upgrade in _discover():
        if version <= applied:
            continue
        await upgrade(db)
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?);",
            (version,),
        )
        await db.commit()
        latest = version
    return latest
