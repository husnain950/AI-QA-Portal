"""Local accounts, scrypt password hashing, and server-side sessions.

No new dependency: ``hashlib.scrypt`` is the stdlib's memory-hard KDF and
``secrets.token_urlsafe`` mints the session token.  Only the token's sha256 is stored, so
a database dump cannot resume anyone's session, and the cookie is the only copy.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.database import DatabaseConnection

ROLES = ("reader", "reviewer", "admin")
RANK = {role: index for index, role in enumerate(ROLES)}
SESSION_COOKIE = "crx_session"
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))

# scrypt parameters. n=2**14 with r=8 costs ~16 MB and a few tens of milliseconds, which
# is the usual interactive-login trade-off.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 64


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str, *, salt: str | None = None) -> tuple[str, str]:
    """(hash, salt), both hex. A fresh random salt unless one is supplied."""
    if len(password or "") < 12:
        raise ValueError("password must be at least 12 characters")
    salt = salt or secrets.token_hex(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return derived.hex(), salt


def verify_password(password: str, *, password_hash: str, salt: str) -> bool:
    try:
        candidate = hashlib.scrypt(
            (password or "").encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=_N,
            r=_R,
            p=_P,
            dklen=_DKLEN,
        ).hex()
    except ValueError:
        return False
    return secrets.compare_digest(candidate, password_hash)


def token_sha(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


async def create_user(
    db: DatabaseConnection,
    *,
    email: str,
    display_name: str,
    password: str,
    role: str = "reader",
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    address = normalize_email(email)
    if "@" not in address:
        raise ValueError("email must contain @")
    password_hash, salt = hash_password(password)
    user_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO users (id, email, display_name, password_hash, password_salt,
                           role, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)
        """,
        (
            user_id,
            address,
            (display_name or address).strip(),
            password_hash,
            salt,
            role,
            _now().isoformat(),
        ),
    )
    return await get_user(db, user_id)


async def get_user(db: DatabaseConnection, user_id: str) -> dict[str, Any] | None:
    async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def authenticate(
    db: DatabaseConnection, email: str, password: str
) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM users WHERE email = ?", (normalize_email(email),)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        # Spend the same work on an unknown address so timing does not enumerate users.
        verify_password(password, password_hash="0" * 128, salt=secrets.token_hex(16))
        return None
    if not row["is_active"]:
        return None
    if not verify_password(
        password, password_hash=row["password_hash"], salt=row["password_salt"]
    ):
        return None
    return dict(row)


async def create_session(
    db: DatabaseConnection,
    user_id: str,
    *,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[str, datetime]:
    """(token, expiry). The token is returned once and never stored in full."""
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(hours=SESSION_HOURS)
    await db.execute(
        """
        INSERT INTO user_sessions
            (token_sha, user_id, created_at, expires_at, last_seen_at, user_agent, client_ip)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_sha(token),
            user_id,
            now.isoformat(),
            expires.isoformat(),
            now.isoformat(),
            (user_agent or "")[:500] or None,
            client_ip,
        ),
    )
    await db.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?", (now.isoformat(), user_id)
    )
    return token, expires


async def resolve_session(db: DatabaseConnection, token: str) -> dict[str, Any] | None:
    """The active principal for a cookie, or None. Expired rows are deleted on sight."""
    if not token:
        return None
    digest = token_sha(token)
    now = _now().isoformat()
    async with db.execute(
        """
        SELECT s.token_sha, s.expires_at, u.id AS user_id, u.email, u.display_name,
               u.role, u.is_active
        FROM user_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_sha = ?
        """,
        (digest,),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    if row["expires_at"] <= now or not row["is_active"]:
        await db.execute("DELETE FROM user_sessions WHERE token_sha = ?", (digest,))
        await db.commit()
        return None
    await db.execute(
        "UPDATE user_sessions SET last_seen_at = ? WHERE token_sha = ?", (now, digest)
    )
    await db.commit()
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


async def revoke_session(db: DatabaseConnection, token: str) -> None:
    await db.execute(
        "DELETE FROM user_sessions WHERE token_sha = ?", (token_sha(token),)
    )


async def revoke_all_sessions(db: DatabaseConnection, user_id: str) -> None:
    await db.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))


def allows(role: str | None, required: str) -> bool:
    return RANK.get(role or "", -1) >= RANK[required]


async def bootstrap_admin(db: DatabaseConnection) -> str | None:
    """Create the first admin from ADMIN_EMAIL/ADMIN_PASSWORD on an empty user table.

    Only ever runs when there are no users at all, so it cannot be used to re-add an
    account someone deliberately disabled.
    """
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        return None
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        if (await cursor.fetchone())[0]:
            return None
    user = await create_user(
        db,
        email=email,
        display_name=os.environ.get("ADMIN_NAME", "").strip() or email,
        password=password,
        role="admin",
    )
    await db.commit()
    return user["email"]
