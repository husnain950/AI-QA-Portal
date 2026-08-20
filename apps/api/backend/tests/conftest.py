"""Test fixtures for the PostgreSQL-backed portal.

Every test runs against one throwaway database (``TEST_DATABASE_URL``, or the
configured ``DATABASE_URL`` with ``_test`` appended to the database name).  Alembic
runs once per session; each test starts from a truncated schema.  Blob storage is
always the filesystem backend under a per-test ``tmp_path``.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx2 as httpx
import pytest
import pytest_asyncio
from alembic import command
from pypdf import PdfWriter
from sqlalchemy import create_engine, text

import backend.database as database
import backend.db_schema as db_schema
import backend.runtime as runtime
from backend.services import auth


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return database.normalize_database_url(explicit)
    base = database.normalize_database_url(
        os.environ.get("DATABASE_URL") or database.DEFAULT_DATABASE_URL
    )
    prefix, _, name = base.rpartition("/")
    return base if name.endswith("_test") else f"{prefix}/{name}_test"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Create the test database if absent and migrate it to the Alembic head."""
    url = _test_database_url()
    prefix, _, name = url.rpartition("/")
    admin = create_engine(f"{prefix}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()

    # Read at call time by get_engine() and _alembic_config(), so the whole test
    # process — routes, services, CLI modules — talks to the test database.
    os.environ["DATABASE_URL"] = url
    os.environ["STORAGE_BACKEND"] = "filesystem"
    os.environ["RATE_LIMITS"] = "off"
    # ASGITransport speaks http://testserver, and a Secure cookie is never sent
    # back over http, so the session would be dropped after every login.
    os.environ["INSECURE_COOKIES"] = "1"
    command.upgrade(database._alembic_config(), "head")
    return url


@pytest.fixture(scope="session")
def _truncation_engine(test_database_url: str):
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


_CALLER_OWNED: list = []


@pytest_asyncio.fixture(autouse=True)
async def clean_database(_truncation_engine):
    """Empty every table declared in db_schema — new tables are covered for free."""
    while _CALLER_OWNED:
        await _CALLER_OWNED.pop().close()
    tables = ", ".join(f'"{table.name}"' for table in db_schema.metadata.sorted_tables)
    with _truncation_engine.begin() as connection:
        # A connection a test left open holds locks TRUNCATE would otherwise wait on
        # forever; fail in ten seconds with a stack trace instead of hanging CI.
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def sample_document(*, second_text: str = "Second section") -> str:
    return json.dumps(
        {
            "metadata": {"total_pages": 3},
            "chapters": [
                {
                    "code": "I",
                    "heading": "General",
                    "sections": [
                        {
                            "code": "1",
                            "heading": "First",
                            "start_page": 1,
                            "end_page": 2,
                            "html": "<p>First section</p>",
                            "plain_text": "First section",
                            "footnotes": [
                                {
                                    "marker": "1",
                                    "page": 1,
                                    "text": "First footnote",
                                    "html": "<span>First footnote</span>",
                                }
                            ],
                        },
                        {
                            "code": "1",
                            "heading": "Repeated code",
                            "start_page": 3,
                            "end_page": 3,
                            "html": f"<p>{second_text}</p>",
                            "plain_text": second_text,
                            "footnotes": [],
                        },
                    ],
                }
            ],
            "schedules": [],
        }
    )


def write_pair(root: Path, name: str = "Test Act") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    with (directory / "act.pdf").open("wb") as target:
        writer.write(target)
    (directory / "act.json").write_text(sample_document(), encoding="utf-8")
    return directory


async def add_annotation(
    db,
    section_id: str,
    *,
    annotation_id: str | None = None,
    highlighted_text: str = "First",
    start: int = 0,
    end: int = 5,
    footnote_id: str | None = None,
    context_before: str | None = None,
    context_after: str | None = None,
    status: str = "open",
):
    """Insert an annotation, deriving ``document_id`` from the section it targets."""
    async with db.execute(
        "SELECT document_id FROM sections WHERE id = ?", (section_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, f"no such section: {section_id}"
    annotation_id = annotation_id or str(uuid4())
    await db.execute(
        """
        INSERT INTO annotations (
            id, document_id, section_id, footnote_id, highlighted_text,
            context_before, context_after, start_offset, end_offset,
            issue_description, severity, created_at, status, anchor_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Check extraction', 'error',
                  '2026-07-29T00:00:00Z', ?, 'anchored')
        """,
        (
            annotation_id,
            row[0],
            section_id,
            footnote_id,
            highlighted_text,
            context_before,
            context_after,
            start,
            end,
            status,
        ),
    )
    return annotation_id


async def seed_document(
    db,
    document_id: str,
    *,
    name: str = "Seeded Act, 2001",
    section_ids: tuple[str, ...] = ("sec-1",),
    text: str = "Body text.",
    with_active_version: bool = False,
) -> tuple[str, ...]:
    """A document and its sections, inserted directly — no PDF, no parse, no blobs.

    For tests about review state, pagination, or inheritance, where the ingest path is
    not what is under test.
    """
    await db.execute(
        """
        INSERT INTO documents (id, name, pdf_filename, json_filename,
                               total_sections, total_pages, uploaded_at, status)
        VALUES (?, ?, 'p.pdf', 'j.json', ?, 1, '2026-01-01', 'pending')
        """,
        (document_id, name, len(section_ids)),
    )
    if with_active_version:
        await db.execute(
            """
            INSERT INTO document_versions (id, document_id, version_no, json_filename,
                                           json_sha256, created_at, total_sections, is_active)
            VALUES (?, ?, 1, 'json/x.json', ?, '2026-01-01', ?, TRUE)
            """,
            (f"ver-{document_id}", document_id, f"sha-{document_id}", len(section_ids)),
        )
    for order, section_id in enumerate(section_ids, 1):
        await db.execute(
            """
            INSERT INTO sections (id, document_id, section_code, section_heading,
                                  sort_order, start_page, plain_text, html_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                section_id,
                document_id,
                str(order),
                f"Section {order}",
                order,
                order,
                text,
                f"<p>{text}</p>",
            ),
        )
    await db.commit()
    return section_ids


async def add_finding(
    db,
    section_id: str,
    document_id: str,
    *,
    detector: str = "glyph_split",
    severity: str = "warning",
    score: float = 10.0,
    triage: str = "new",
    fingerprint: str | None = None,
) -> int:
    await db.execute(
        """
        INSERT INTO findings (section_id, document_id, detector, detector_version,
                              fingerprint, severity, score, triage,
                              first_seen_at, last_seen_at, detail_json)
        VALUES (?, ?, ?, '1', ?, ?, ?, ?, '2026-01-01', '2026-01-01', ?)
        """,
        (
            section_id,
            document_id,
            detector,
            fingerprint or f"{detector}:{section_id}",
            severity,
            score,
            triage,
            json.dumps({"assertion": f"{detector} on {section_id}"}),
        ),
    )
    async with db.execute(
        "SELECT id FROM findings WHERE section_id = ? AND detector = ? AND fingerprint = ?",
        (section_id, detector, fingerprint or f"{detector}:{section_id}"),
    ) as cursor:
        return int((await cursor.fetchone())["id"])


async def active_version_id(db, document_id: str) -> str:
    """The If-Match value every version-replacing route now requires."""
    async with db.execute(
        "SELECT id FROM document_versions WHERE document_id = ? AND is_active",
        (document_id,),
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, f"no active version for {document_id}"
    return row["id"]


async def open_connection() -> database.DatabaseConnection:
    """A connection for helpers that return a live ``db``; closed before the next test."""
    connection = database.DatabaseConnection(await database.get_engine().connect())
    _CALLER_OWNED.append(connection)
    return connection


@pytest_asyncio.fixture
async def runtime_sandbox(monkeypatch, tmp_path):
    """A migrated, empty database plus a private filesystem blob root."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime, "UPLOAD_DIR", str(upload_dir))
    return {"upload_dir": upload_dir, "root": tmp_path}


TEST_PASSWORD = "correct-horse-battery-staple"
ADMIN_EMAIL = "tester@crx.test"


@pytest_asyncio.fixture
async def accounts(runtime_sandbox):
    """One account per role. Emails double as the actor names in the audit trail."""
    created = {}
    async with database.database_connection() as db:
        for role in ("reader", "reviewer", "admin"):
            email = ADMIN_EMAIL if role == "admin" else f"{role}@crx.test"
            await auth.create_user(
                db, email=email, display_name=role, password=TEST_PASSWORD, role=role
            )
            created[role] = email
        await db.commit()
    return created


@pytest_asyncio.fixture
async def sign_in(accounts):
    """Factory: an HTTP session logged in as the given role.

    ASGITransport keeps the app on this test's event loop, so it shares the one async
    engine; TestClient would run it on a thread of its own and hand the same pooled
    connections to two loops.
    """
    from backend.main import app

    sessions = []

    async def _sign_in(role: str = "admin", *, email: str | None = None):
        session = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        sessions.append(session)
        response = await session.post(
            "/api/auth/login",
            json={"email": email or accounts[role], "password": TEST_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return session

    yield _sign_in
    for session in sessions:
        await session.aclose()


@pytest_asyncio.fixture
async def anonymous(runtime_sandbox):
    """An HTTP session with no cookie, for checking that a route is not public."""
    from backend.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as session:
        yield session


@pytest_asyncio.fixture
async def client(sign_in):
    """The default HTTP session: signed in as an admin."""
    return await sign_in("admin")


@pytest_asyncio.fixture
async def db(runtime_sandbox):
    async with database.database_connection() as connection:
        yield connection
