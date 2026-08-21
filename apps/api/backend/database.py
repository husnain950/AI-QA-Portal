"""PostgreSQL database access with an aiosqlite-shaped transition facade.

Routes and services historically issued qmark-parameterized SQL directly.  The facade
keeps those call sites working while the domain services move to SQLAlchemy statements;
the engine, transactions, pooling, migrations, and production database are PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from psycopg import InterfaceError as PsycopgInterfaceError
from psycopg import OperationalError as PsycopgOperationalError
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://crx:crx@127.0.0.1:5432/crx"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
# Compatibility names used by command-line modules while they are ported.
DB_PATH = DATABASE_URL
DB_DIR = ""

_engine: AsyncEngine | None = None
_engine_url: str | None = None

# Login is the first request that opens a connection. Without these, a wrong
# DATABASE_URL or a sleeping Postgres waits on TCP until the browser aborts at 15s.
UNREACHABLE_DB_ERRORS = (
    OperationalError,
    InterfaceError,
    SATimeoutError,
    PsycopgOperationalError,
    PsycopgInterfaceError,
)
DATABASE_UNREACHABLE_MESSAGE = "the database is not reachable"


def db_connect_timeout() -> int:
    return int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))


def db_pool_timeout() -> int:
    return int(os.environ.get("DB_POOL_TIMEOUT", "5"))


def engine_settings() -> dict[str, Any]:
    """Fail-fast pool/connect options so a dead database cannot hang a request."""
    return {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": db_pool_timeout(),
        "connect_args": {"connect_timeout": db_connect_timeout()},
    }


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def get_engine() -> AsyncEngine:
    global _engine, _engine_url
    url = normalize_database_url(os.environ.get("DATABASE_URL", DATABASE_URL))
    if _engine is None or _engine_url != url:
        _engine = create_async_engine(url, **engine_settings())
        _engine_url = url
    return _engine


async def dispose_engine() -> None:
    global _engine, _engine_url
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _engine_url = None


class DatabaseRow(Mapping[str, Any]):
    """Row supporting both SQLite-style integer and mapping access."""

    def __init__(self, row: Any):
        self._values = tuple(row)
        self._mapping = dict(row._mapping)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def keys(self):
        return self._mapping.keys()


class DatabaseCursor:
    def __init__(self, rows: list[DatabaseRow], *, rowcount: int = -1):
        self._rows = rows
        self._index = 0
        self.rowcount = rowcount
        self.lastrowid: int | None = None

    async def fetchone(self) -> DatabaseRow | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    async def fetchall(self) -> list[DatabaseRow]:
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows


def _qmark(sql: str, params: Sequence[Any] | Mapping[str, Any] | None):
    if params is None or isinstance(params, Mapping):
        return sql, params or {}
    values = list(params)
    pieces: list[str] = []
    binds: dict[str, Any] = {}
    quote: str | None = None
    index = 0
    for char in sql:
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            pieces.append(char)
        elif char == "?" and quote is None:
            if index >= len(values):
                raise ValueError("not enough SQL parameters")
            name = f"p{index}"
            pieces.append(f":{name}")
            binds[name] = values[index]
            index += 1
        else:
            pieces.append(char)
    if index != len(values):
        raise ValueError("too many SQL parameters")
    return "".join(pieces), binds


class _ExecuteContext:
    def __init__(self, connection: "DatabaseConnection", sql: str, params: Any):
        self._connection = connection
        self._sql = sql
        self._params = params
        self._cursor: DatabaseCursor | None = None

    async def _run(self) -> DatabaseCursor:
        if self._cursor is None:
            self._cursor = await self._connection._execute(self._sql, self._params)
        return self._cursor

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self) -> DatabaseCursor:
        return await self._run()

    async def __aexit__(self, *_exc) -> None:
        return None


class DatabaseConnection:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection
        self.row_factory = DatabaseRow

    def execute(self, sql: str, params: Any = None) -> _ExecuteContext:
        return _ExecuteContext(self, sql, params)

    async def _execute(self, sql: str, params: Any = None) -> DatabaseCursor:
        statement, binds = _qmark(sql, params)
        result = await self._connection.execute(text(statement), binds)
        rows = [DatabaseRow(row) for row in result.fetchall()] if result.returns_rows else []
        return DatabaseCursor(rows, rowcount=result.rowcount)

    async def executemany(self, sql: str, values: Iterable[Sequence[Any]]) -> DatabaseCursor:
        rows = list(values)
        if not rows:
            return DatabaseCursor([], rowcount=0)
        statement, _ = _qmark(sql, rows[0])
        bind_rows = [_qmark(sql, row)[1] for row in rows]
        result = await self._connection.execute(text(statement), bind_rows)
        return DatabaseCursor([], rowcount=result.rowcount)

    async def close(self) -> None:
        await self._connection.close()

    async def commit(self) -> None:
        await self._connection.commit()

    async def rollback(self) -> None:
        await self._connection.rollback()


async def get_db() -> AsyncIterator[DatabaseConnection]:
    async with get_engine().connect() as connection:
        yield DatabaseConnection(connection)


class database_connection:
    """Async context manager for CLI and worker code outside dependency injection."""

    def __init__(self):
        self._context = None
        self._connection = None

    async def __aenter__(self) -> DatabaseConnection:
        self._context = get_engine().connect()
        self._connection = await self._context.__aenter__()
        return DatabaseConnection(self._connection)

    async def __aexit__(self, *exc) -> None:
        await self._context.__aexit__(*exc)


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parent
    config = Config()
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", normalize_database_url(os.environ.get("DATABASE_URL", DATABASE_URL)))
    return config


async def init_db() -> None:
    """Upgrade the configured PostgreSQL database to the current Alembic head."""
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

