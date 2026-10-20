"""Configuracion por variables de entorno (se leen en cada peticion, facil de testear)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    twitch_client_id: str | None
    twitch_client_secret: str | None
    auth_db_path: Path
    session_cookie_secure: bool
    login_username: str | None
    login_password: str | None
    public_origin: str | None
    twitter_handle: str | None


def _public_origin() -> str | None:
    origin = os.environ.get("TWITCH_M3U_PUBLIC_ORIGIN", "").strip()
    if not origin:
        return None
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(
            "TWITCH_M3U_PUBLIC_ORIGIN must be an absolute HTTP(S) origin "
            "without a path, query, or fragment."
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "TWITCH_M3U_PUBLIC_ORIGIN must be an absolute HTTP(S) origin "
            "without a path, query, or fragment."
        )
    return origin.rstrip("/")


def get_settings() -> Settings:
    data_dir = Path(os.environ.get("TWITCH_M3U_DATA_DIR", "data")).resolve()
    return Settings(
        data_dir=data_dir,
        twitch_client_id=os.environ.get("TWITCH_CLIENT_ID") or None,
        twitch_client_secret=os.environ.get("TWITCH_CLIENT_SECRET") or None,
        auth_db_path=Path(
            os.environ.get(
                "TWITCH_M3U_AUTH_DB",
                str(data_dir / "auth.sqlite3"),
            )
        ).resolve(),
        session_cookie_secure=(
            os.environ.get("TWITCH_M3U_COOKIE_SECURE", "true").strip().lower()
            not in {"0", "false", "no", "off"}
        ),
        login_username=os.environ.get("TWITCH_M3U_LOGIN_USERNAME") or None,
        login_password=os.environ.get("TWITCH_M3U_LOGIN_PASSWORD") or None,
        public_origin=_public_origin(),
        twitter_handle=os.environ.get("TWITCH_M3U_TWITTER_HANDLE", "").strip() or None,
    )
