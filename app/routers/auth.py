"""Login and browser-session routes."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError

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


@router.post(
    "/auth/login",
    response_model=dict[str, str],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": LoginRequest.model_json_schema()},
                "application/x-www-form-urlencoded": {
                    "schema": LoginRequest.model_json_schema()
                },
            },
        }
    },
)
async def login(
    request: Request, response: Response
) -> dict[str, str] | RedirectResponse:
    require_same_origin(request)
    raw_body = await request.body()
    if len(raw_body) > 16_384:
        raise HTTPException(status_code=413, detail="Login request is too large")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    is_form = content_type == "application/x-www-form-urlencoded"
    try:
        if content_type == "application/json":
            payload = json.loads(raw_body)
        elif is_form:
            parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            payload = {name: values[-1] for name, values in parsed.items()}
        else:
            raise HTTPException(
                status_code=415,
                detail="Login requires JSON or URL-encoded form data",
            )
        body = LoginRequest.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            errors = exc.errors()
        else:
            errors = [
                {
                    "loc": ("body",),
                    "msg": "Invalid request body",
                    "type": "value_error",
                }
            ]
        raise RequestValidationError(errors) from exc

    settings = get_settings()
    username = body.username.strip()
    if not verify_user(settings.auth_db_path, username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        session_token, _expires_at = create_session(settings.auth_db_path, username)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc
    cookie_options = {
        "max_age": SESSION_TTL_SECONDS,
        "httponly": True,
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    if is_form:
        redirect = RedirectResponse(_safe_next_path(body.next), status_code=303)
        redirect.set_cookie(SESSION_COOKIE, session_token, **cookie_options)
        redirect.headers["Cache-Control"] = "no-store"
        return redirect
    response.set_cookie(SESSION_COOKIE, session_token, **cookie_options)
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
