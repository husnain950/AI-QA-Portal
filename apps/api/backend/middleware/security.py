"""Attribution, IP throttling, security headers, and structured request logs."""

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


def _limit_for(method: str, path: str) -> Limit:
    if "/ai-fix" in path or "/jobs/ai_proposal" in path:
        return AI
    if "/corpus/sync" in path or "/jobs/corpus_sync" in path:
        return SYNC
    if (
        method == "DELETE"
        or "/uploads" in path
        or "/versions" in path
        or (method == "POST" and path == "/api/v2/documents")
    ):
        return HEAVY
    if method != "GET" or path.endswith("/search") or "/search?" in path:
        return REVIEW
    return READ


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.limiter = WindowLimiter()

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

        attribution_exempt = path in {"/api/v2/csp-reports"}
        if method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api") and not attribution_exempt:
            if not request.headers.get("x-reviewer", "").strip():
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": "reviewer_required",
                        "detail": "X-Reviewer is required for every mutation (unverified attribution)",
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )

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
                    "actor": request.headers.get("x-reviewer", "").strip() or None,
                    "client_ip": ip,
                },
                separators=(",", ":"),
            )
        )
        return response
