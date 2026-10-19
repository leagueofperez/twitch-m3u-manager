"""Optional HTTP Basic authentication."""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_settings

_basic = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return

    ok = (
        credentials is not None
        and secrets.compare_digest(credentials.username.encode(), settings.auth_user.encode())
        and secrets.compare_digest(credentials.password.encode(), settings.auth_password.encode())
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="twitch-m3u-manager"'},
        )
