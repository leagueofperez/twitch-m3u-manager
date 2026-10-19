"""Login and browser-session routes."""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..auth_store import (
    SESSION_TTL_SECONDS,
    create_session,
    delete_session,
    verify_user,
)
from ..config import get_settings
from ..security import SESSION_COOKIE, authenticate_request, require_same_origin
from ..templating import templates

router = APIRouter(tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
    next: str = Field(default="/", max_length=2048)


def _safe_next_path(path: str) -> str:
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "\\" in path
        or parsed.scheme
        or parsed.netloc
    ):
        return "/"
    return path


@router.get("/login", include_in_schema=False)
def login_page(request: Request, next: str = "/"):
    if authenticate_request(request):
        return RedirectResponse(_safe_next_path(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": _safe_next_path(next)},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    require_same_origin(request)
    settings = get_settings()
    username = body.username.strip()
    if not verify_user(settings.auth_db_path, username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        session_token, _expires_at = create_session(settings.auth_db_path, username)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"redirect": _safe_next_path(body.next)}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    require_same_origin(request)
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        delete_session(get_settings().auth_db_path, session_token)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=get_settings().session_cookie_secure,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"redirect": "/login"}
