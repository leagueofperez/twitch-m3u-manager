"""API-key and browser-session authentication."""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from .auth_store import PRIVATE, PUBLIC, APIKey, get_api_key, get_session
from .config import get_settings

SESSION_COOKIE = "tmm_session"


def require_same_origin(request: Request) -> None:
    expected = f"{request.url.scheme}://{request.url.netloc}"
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    supplied_origin = origin or (
        f"{urlsplit(referer).scheme}://{urlsplit(referer).netloc}" if referer else None
    )
    if supplied_origin != expected:
        raise HTTPException(status_code=403, detail="Cross-origin request denied")


def authenticate_request(request: Request) -> APIKey | None:
    settings = get_settings()
    api_key = request.headers.get("x-api-key")
    authorization = request.headers.get("authorization")
    if api_key is None and authorization:
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() == "bearer" and credential:
            api_key = credential
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
            )

    if api_key is not None:
        key = get_api_key(settings.auth_db_path, api_key)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        request.state.api_key_auth = True
        return key

    if request.method == "GET" and request.url.path.startswith("/m3u/"):
        api_key = request.query_params.get("apiKey")
        if api_key is not None:
            key = get_api_key(settings.auth_db_path, api_key)
            if key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key",
                )
            if key.kind != PUBLIC:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Private API keys cannot be used in the query string; "
                        "send them in the X-API-Key header"
                    ),
                )
            request.state.api_key_auth = True
            return key

    session_token = request.cookies.get(SESSION_COOKIE)
    key = get_session(settings.auth_db_path, session_token) if session_token else None
    if key:
        request.state.api_key_auth = False
    return key


def require_read(request: Request) -> APIKey:
    key = authenticate_request(request)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key or login required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.api_key_kind = key.kind
    return key


def require_write(request: Request) -> APIKey:
    key = require_read(request)
    if key.kind != PRIVATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A private API key is required",
        )
    if not request.state.api_key_auth:
        require_same_origin(request)
    return key
