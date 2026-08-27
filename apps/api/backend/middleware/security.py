"""Authentication, authorization, IP throttling, security headers, request logs.

One place decides who a request is and whether its role may make it, so no route can
be added without an access decision. Routes read the resolved principal from
``request.state`` (see ``backend.deps.require_reviewer``) and never from a header.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.database import (
    DATABASE_UNREACHABLE_MESSAGE,
    UNREACHABLE_DB_ERRORS,
    database_connection,
)
from backend.services import auth

logger = logging.getLogger("crx.request")


@dataclass(frozen=True)
class Limit:
    count: int
    seconds: int
    name: str


READ = Limit(120, 60, "read")
REVIEW = Limit(60, 60, "review")
HEAVY = Limit(10, 3600, "heavy")
SYNC = Limit(2, 3600, "sync")
AI = Limit(20, 3600, "ai")


class WindowLimiter:
    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, ip: str, limit: Limit, now: float) -> int | None:
        key = (ip, limit.name)
        with self._lock:
            window = self._windows[key]
            cutoff = now - limit.seconds
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit.count:
                return max(1, int(window[0] + limit.seconds - now))
            window.append(now)
        return None


def _client_ip(request) -> str:
    if os.environ.get("TRUST_PROXY_HEADERS", "1") == "1":
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


# Paths anyone may reach: the login form itself, the liveness/readiness probes the
# platform calls with no session, and the CSP report sink the browser posts to.
PUBLIC_PATHS = frozenset({"/api/auth/login", "/api/v2/csp-reports"})
PUBLIC_PREFIXES = ("/health",)

# Corpus shape is the admin's to change: upload, delete, roll back a version, re-sync,
# run a job, read operator diagnostics. Reviewing content — verdicts, annotations,
# footnotes, triage, AI fixes — is the reviewer's.
_ADMIN_SUBSTRINGS = (
    "/uploads",
    "/versions",
    "/replace-json",
    "/corpus/sync",
    "/api/v2/jobs",
    "/api/v2/detectors/run",
    "/api/v2/operator",
    "/api/v2/statute-families",
    "/identity",
)
_ADMIN_READ_SUBSTRINGS = ("/api/v2/operator", "/api/v2/metrics", "/api/v2/system")


def required_role(method: str, path: str) -> str | None:
    """The minimum role for a request, or None when the path is public."""
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return None
    if method == "GET" or method == "HEAD":
        if any(fragment in path for fragment in _ADMIN_READ_SUBSTRINGS):
            return "admin"
        return "reader"
    if not path.startswith("/api"):
        return "reader"
    if method == "DELETE" or (method == "POST" and path == "/api/v2/documents"):
        return "admin"
    if any(fragment in path for fragment in _ADMIN_SUBSTRINGS):
        return "admin"
    if path in {"/api/auth/logout"}:
        return "reader"
    return "reviewer"


def _limit_for(method: str, path: str) -> Limit:
    if "/ai-fix" in path or "/jobs/ai_proposal" in path:
        return AI
    if "/corpus/sync" in path or "/jobs/corpus_sync" in path:
        return SYNC
    if method == "DELETE" or (method == "POST" and path == "/api/v2/documents"):
        return HEAVY
    # Blob reads (GET/HEAD /uploads/<key>) are static fetches: pdf.js range-streams
    # one document as dozens of 64 KB requests, so the write-tier HEAVY bucket
    # (10/hour) 429s every viewer mid-document. Only upload *writes* belong there.
    if method not in ("GET", "HEAD") and ("/uploads" in path or "/versions" in path):
        return HEAVY
    if method not in ("GET", "HEAD") or path.endswith("/search") or "/search?" in path:
        return REVIEW
    return READ


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.limiter = WindowLimiter()

    @staticmethod
    def _metrics_token(request, path: str) -> bool:
        """A Prometheus scraper has no session, so /metrics keeps a shared-token door."""
        expected = os.environ.get("METRICS_TOKEN", "")
        return bool(
            expected
            and path == "/api/v2/metrics"
            and request.headers.get("x-metrics-token") == expected
        )

    @staticmethod
    async def _principal(request):
        token = request.cookies.get(auth.SESSION_COOKIE, "")
        if not token:
            return None
        async with database_connection() as db:
            return await auth.resolve_session(db, token)

    async def dispatch(self, request, call_next):
        started = time.monotonic()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        path = request.url.path
        method = request.method.upper()
        ip = _client_ip(request)

        limit = _limit_for(method, path)
        retry_after = (
            None
            if os.environ.get("RATE_LIMITS") == "off"
            else self.limiter.check(ip, limit, time.time())
        )
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "detail": f"{limit.name} request limit exceeded",
                    "request_id": request_id,
                },
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )

        request.state.principal = None
        request.state.actor = None
        request.state.role = None
        required = required_role(method, path)
        if required is not None and not self._metrics_token(request, path):
            try:
                principal = await self._principal(request)
            except UNREACHABLE_DB_ERRORS:
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "database_unreachable",
                        "detail": {
                            "code": "database_unreachable",
                            "message": DATABASE_UNREACHABLE_MESSAGE,
                        },
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )
            if principal is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "code": "unauthenticated",
                        "detail": "sign in to use this API",
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )
            if not auth.allows(principal["role"], required):
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "forbidden",
                        "detail": f"this action needs the {required} role",
                        "role": principal["role"],
                        "required_role": required,
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )
            request.state.principal = principal
            # Attribution comes from the session, never from a client-supplied header.
            request.state.actor = principal["email"]
            request.state.role = principal["role"]

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        policy = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
            "font-src 'self'; connect-src 'self' ws: wss:; worker-src 'self' blob:"
        )
        header = "Content-Security-Policy" if os.environ.get("CSP_ENFORCE") == "1" else "Content-Security-Policy-Report-Only"
        response.headers[header] = policy
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "actor": getattr(request.state, "actor", None),
                    "role": getattr(request.state, "role", None),
                    "client_ip": ip,
                },
                separators=(",", ":"),
            )
        )
        return response
