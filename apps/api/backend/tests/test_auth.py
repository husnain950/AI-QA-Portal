"""Who a request is, and what that lets it do.

Before this, `X-Reviewer` was documented as attribution and nothing else: any caller
could upload, delete, re-sync, roll back a version, approve legal text, or spend money on
AI work, under any name it liked. Identity now comes from a server-side session, and the
role decides what the session may do.
"""

import time

import httpx2 as httpx
import pytest

from backend.database import (
    DATABASE_UNREACHABLE_MESSAGE,
    database_connection,
    dispose_engine,
    engine_settings,
)
from backend.services import auth
from backend.tests.conftest import (
    ADMIN_EMAIL,
    TEST_PASSWORD,
    seed_document,
)

DOCUMENT_ID = "doc-auth"
SECTION_ID = "sec-auth"


# ----------------------------------------------------------------- password hashing


def test_a_password_verifies_only_against_its_own_salt():
    digest, salt = auth.hash_password("correct-horse-battery")
    assert auth.verify_password("correct-horse-battery", password_hash=digest, salt=salt)
    assert not auth.verify_password("wrong-horse-battery", password_hash=digest, salt=salt)
    _, other_salt = auth.hash_password("correct-horse-battery")
    assert not auth.verify_password(
        "correct-horse-battery", password_hash=digest, salt=other_salt
    ), "the salt is part of the secret, so a swapped salt must not verify"


def test_the_same_password_hashes_differently_for_two_people():
    first, first_salt = auth.hash_password("shared-team-password")
    second, second_salt = auth.hash_password("shared-team-password")
    assert first != second and first_salt != second_salt


def test_a_short_password_is_refused_before_it_is_stored():
    with pytest.raises(ValueError, match="12 characters"):
        auth.hash_password("hunter2")


def test_a_corrupt_salt_is_a_failed_verification_not_a_crash():
    digest, _ = auth.hash_password("correct-horse-battery")
    assert not auth.verify_password("correct-horse-battery", password_hash=digest, salt="zz")


def test_role_ranking_is_cumulative():
    assert auth.allows("admin", "reviewer") and auth.allows("admin", "reader")
    assert auth.allows("reviewer", "reader")
    assert not auth.allows("reviewer", "admin")
    assert not auth.allows("reader", "reviewer")
    assert not auth.allows(None, "reader")


# ------------------------------------------------------------------------- accounts


async def test_an_account_is_created_normalized_and_uniquely(runtime_sandbox):
    async with database_connection() as db:
        user = await auth.create_user(
            db,
            email="  Alice@Example.COM ",
            display_name="Alice",
            password=TEST_PASSWORD,
            role="reviewer",
        )
        await db.commit()
        assert user["email"] == "alice@example.com", "case and spacing cannot fork an account"

        with pytest.raises(Exception):
            await auth.create_user(
                db, email="alice@example.com", display_name="Impostor",
                password=TEST_PASSWORD, role="admin",
            )
        await db.rollback()


async def test_an_unknown_role_or_email_is_refused(runtime_sandbox):
    async with database_connection() as db:
        with pytest.raises(ValueError, match="role must be"):
            await auth.create_user(
                db, email="a@b.com", display_name="a", password=TEST_PASSWORD, role="root"
            )
        with pytest.raises(ValueError, match="@"):
            await auth.create_user(
                db, email="nope", display_name="a", password=TEST_PASSWORD
            )


async def test_authenticate_rejects_a_wrong_password_and_a_disabled_account(runtime_sandbox):
    async with database_connection() as db:
        user = await auth.create_user(
            db, email="bob@example.com", display_name="Bob", password=TEST_PASSWORD
        )
        await db.commit()

        assert await auth.authenticate(db, "bob@example.com", TEST_PASSWORD)
        assert await auth.authenticate(db, "bob@example.com", "nope") is None
        assert await auth.authenticate(db, "nobody@example.com", TEST_PASSWORD) is None

        await db.execute("UPDATE users SET is_active = FALSE WHERE id = ?", (user["id"],))
        await db.commit()
        assert await auth.authenticate(db, "bob@example.com", TEST_PASSWORD) is None


async def test_only_the_token_digest_is_stored(runtime_sandbox):
    async with database_connection() as db:
        user = await auth.create_user(
            db, email="carol@example.com", display_name="Carol", password=TEST_PASSWORD
        )
        token, _ = await auth.create_session(db, user["id"])
        await db.commit()

        async with db.execute("SELECT token_sha FROM user_sessions") as cursor:
            stored = (await cursor.fetchone())["token_sha"]
        assert token not in stored
        assert stored == auth.token_sha(token)
        assert (await auth.resolve_session(db, token))["email"] == "carol@example.com"
        assert await auth.resolve_session(db, "some-other-token") is None


async def test_an_expired_session_is_rejected_and_cleaned_up(runtime_sandbox):
    async with database_connection() as db:
        user = await auth.create_user(
            db, email="dan@example.com", display_name="Dan", password=TEST_PASSWORD
        )
        token, _ = await auth.create_session(db, user["id"])
        await db.execute(
            "UPDATE user_sessions SET expires_at = '2020-01-01T00:00:00+00:00'"
        )
        await db.commit()

        assert await auth.resolve_session(db, token) is None
        async with db.execute("SELECT COUNT(*) FROM user_sessions") as cursor:
            assert (await cursor.fetchone())[0] == 0


async def test_disabling_an_account_kills_its_live_sessions(runtime_sandbox):
    async with database_connection() as db:
        user = await auth.create_user(
            db, email="erin@example.com", display_name="Erin", password=TEST_PASSWORD
        )
        token, _ = await auth.create_session(db, user["id"])
        await db.commit()

        await db.execute("UPDATE users SET is_active = FALSE WHERE id = ?", (user["id"],))
        await db.commit()
        assert await auth.resolve_session(db, token) is None


async def test_bootstrap_creates_the_first_admin_and_then_stays_out_of_the_way(
    runtime_sandbox, monkeypatch
):
    monkeypatch.setenv("ADMIN_EMAIL", "root@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", TEST_PASSWORD)
    async with database_connection() as db:
        assert await auth.bootstrap_admin(db) == "root@example.com"
        async with db.execute("SELECT role FROM users") as cursor:
            assert [row["role"] for row in await cursor.fetchall()] == ["admin"]

        # A second boot must not resurrect an account an operator removed on purpose.
        assert await auth.bootstrap_admin(db) is None
        await db.execute("UPDATE users SET is_active = FALSE")
        await db.commit()
        assert await auth.bootstrap_admin(db) is None


async def test_bootstrap_does_nothing_without_credentials(runtime_sandbox, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    async with database_connection() as db:
        assert await auth.bootstrap_admin(db) is None


# ----------------------------------------------------------------------- login flow


async def test_login_sets_a_session_cookie_and_me_resolves_it(runtime_sandbox, accounts, anonymous):
    response = await anonymous.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie, "script must not be able to read the session"
    assert "SameSite=strict" in cookie.replace("samesite", "SameSite"), (
        "SameSite=Strict is the CSRF defence for this cookie"
    )

    me = await anonymous.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL
    assert me.json()["role"] == "admin"


async def test_a_bad_login_says_the_same_thing_either_way(runtime_sandbox, accounts, anonymous):
    wrong_password = await anonymous.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "not-it-at-all"}
    )
    unknown_user = await anonymous.post(
        "/api/auth/login", json={"email": "ghost@crx.test", "password": TEST_PASSWORD}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json(), (
        "a different message would let an attacker enumerate accounts"
    )
    assert "set-cookie" not in wrong_password.headers


def test_engine_settings_fail_fast_when_postgres_is_gone():
    settings = engine_settings()
    assert settings["connect_args"]["connect_timeout"] == 5
    assert settings["pool_timeout"] == 5


async def test_login_returns_503_when_the_database_is_unreachable(
    runtime_sandbox, monkeypatch
):
    """A black-hole DATABASE_URL used to hang until the browser's 15s abort."""
    from backend.main import app

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://crx:crx@192.0.2.1:5432/crx")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "2")
    await dispose_engine()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            timeout=15,
        ) as session:
            started = time.monotonic()
            response = await session.post(
                "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": TEST_PASSWORD},
            )
            assert time.monotonic() - started < 12, "login hung instead of failing fast"
            assert response.status_code == 503
            body = response.json()
            detail = body.get("detail")
            message = detail.get("message") if isinstance(detail, dict) else detail
            assert message == DATABASE_UNREACHABLE_MESSAGE
    finally:
        await dispose_engine()


async def test_logout_revokes_the_session_server_side(runtime_sandbox, client):
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await client.post("/api/auth/logout")).status_code == 204

    async with database_connection() as db:
        async with db.execute("SELECT COUNT(*) FROM user_sessions") as cursor:
            assert (await cursor.fetchone())[0] == 0, "not just a cleared cookie"
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_a_tampered_cookie_is_not_a_session(runtime_sandbox, accounts, anonymous):
    await anonymous.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": TEST_PASSWORD}
    )
    anonymous.cookies.set(auth.SESSION_COOKIE, "forged-token-value")
    assert (await anonymous.get("/api/auth/me")).status_code == 401


# ---------------------------------------------------------------------------- RBAC


async def test_every_api_path_needs_a_session(runtime_sandbox, anonymous):
    for method, path in (
        ("GET", "/api/documents"),
        ("GET", "/api/v2/documents"),
        ("GET", "/api/v2/findings"),
        ("PATCH", "/api/documents/doc-1/sections/sec-1/status"),
        ("POST", "/api/corpus/sync"),
        ("DELETE", "/api/documents/doc-1"),
        ("GET", "/api/v2/operator/audit-events"),
    ):
        response = await anonymous.request(method, path, json={})
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"


async def test_the_probes_and_the_login_form_stay_open(runtime_sandbox, anonymous):
    for path in ("/health/live", "/health/ready"):
        assert (await anonymous.get(path)).status_code in (200, 503), path
    assert (await anonymous.post("/api/v2/csp-reports", content=b"{}")).status_code == 204


async def test_a_reader_can_look_but_not_touch(runtime_sandbox, sign_in):
    async with database_connection() as db:
        await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,), with_active_version=True)

    reader = await sign_in("reader")
    assert (await reader.get("/api/v2/documents")).status_code == 200
    assert (await reader.get(f"/api/documents/{DOCUMENT_ID}")).status_code == 200

    blocked = await reader.patch(
        f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}/status", json={"review_status": "approved"}
    )
    assert blocked.status_code == 403
    assert blocked.json()["required_role"] == "reviewer"


async def test_a_reviewer_reviews_but_does_not_reshape_the_corpus(runtime_sandbox, sign_in):
    async with database_connection() as db:
        await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,), with_active_version=True)

    reviewer = await sign_in("reviewer")
    allowed = await reviewer.patch(
        f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}/status", json={"review_status": "approved"}
    )
    assert allowed.status_code == 200, allowed.text

    for method, path in (
        ("POST", "/api/corpus/sync"),
        ("DELETE", f"/api/documents/{DOCUMENT_ID}"),
        ("POST", "/api/v2/jobs/detectors"),
        ("GET", "/api/v2/operator/audit-events"),
    ):
        response = await reviewer.request(method, path, json={})
        assert response.status_code == 403, f"{method} {path} answered {response.status_code}"
        assert response.json()["required_role"] == "admin"


async def test_an_admin_reaches_the_operator_surface(runtime_sandbox, client):
    assert (await client.get("/api/v2/operator/audit-events")).status_code == 200
    assert (await client.get("/api/v2/operator/backups")).status_code == 200
    assert (await client.get("/api/v2/system")).status_code == 200


async def test_metrics_answers_a_scraper_with_a_token_and_nobody_else(
    runtime_sandbox, anonymous, monkeypatch
):
    monkeypatch.setenv("METRICS_TOKEN", "scrape-me")
    assert (await anonymous.get("/api/v2/metrics")).status_code == 401

    async with database_connection() as db:
        await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,))

    scraped = await anonymous.get(
        "/api/v2/metrics", headers={"X-Metrics-Token": "scrape-me"}
    )
    assert scraped.status_code == 200
    assert "crx_documents" in scraped.text

    wrong = await anonymous.get("/api/v2/metrics", headers={"X-Metrics-Token": "guess"})
    assert wrong.status_code == 401


async def test_the_actor_recorded_is_the_session_not_a_header(runtime_sandbox, sign_in):
    """The header used to be the whole identity; now it is ignored."""
    async with database_connection() as db:
        await seed_document(db, DOCUMENT_ID, section_ids=(SECTION_ID,), with_active_version=True)

    reviewer = await sign_in("reviewer")
    response = await reviewer.patch(
        f"/api/documents/{DOCUMENT_ID}/sections/{SECTION_ID}/status",
        json={"review_status": "approved"},
        headers={"X-Reviewer": "somebody-important"},
    )
    assert response.status_code == 200

    async with database_connection() as db:
        async with db.execute(
            "SELECT actor FROM review_events ORDER BY id DESC LIMIT 1"
        ) as cursor:
            assert (await cursor.fetchone())["actor"] == "reviewer@crx.test"
