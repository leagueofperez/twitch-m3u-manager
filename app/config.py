"""Configuracion por variables de entorno (se leen en cada peticion, facil de testear)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    twitch_client_id: str | None
    twitch_client_secret: str | None
    auth_db_path: Path
    session_cookie_secure: bool
    login_username: str | None
    login_password: str | None


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
    )
