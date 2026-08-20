"""Login, logout, and the current principal."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.database import DatabaseConnection, get_db
from backend.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


def _secure_cookies() -> bool:
    """Off only when explicitly asked for, so a misconfigured prod still sets Secure."""
    return os.environ.get("INSECURE_COOKIES") != "1"


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseConnection = Depends(get_db),
):
    user = await auth.authenticate(db, body.email, body.password)
    if user is None:
        # One message for unknown address, wrong password, and disabled account.
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "email or password is incorrect"},
        )
    token, expires = await auth.create_session(
        db,
        user["id"],
        user_agent=request.headers.get("user-agent"),
        client_ip=request.client.host if request.client else None,
    )
    await db.commit()
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        httponly=True,
        secure=_secure_cookies(),
        samesite="strict",
        max_age=auth.SESSION_HOURS * 3600,
        path="/",
    )
    return {
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "expires_at": expires.isoformat(),
    }


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: DatabaseConnection = Depends(get_db),
):
    token = request.cookies.get(auth.SESSION_COOKIE, "")
    if token:
        await auth.revoke_session(db, token)
        await db.commit()
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


@router.get("/me")
async def me(request: Request):
    principal = getattr(request.state, "principal", None)
    if not principal:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated"})
    return principal
