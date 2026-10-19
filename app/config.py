"""Configuracion por variables de entorno (se leen en cada peticion, facil de testear)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    auth_user: str | None
    auth_password: str | None
    twitch_client_id: str | None
    twitch_client_secret: str | None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_user and self.auth_password)


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("TWITCH_M3U_DATA_DIR", "data")).resolve(),
        auth_user=os.environ.get("TWITCH_M3U_AUTH_USER") or None,
        auth_password=os.environ.get("TWITCH_M3U_AUTH_PASSWORD") or None,
        twitch_client_id=os.environ.get("TWITCH_CLIENT_ID") or None,
        twitch_client_secret=os.environ.get("TWITCH_CLIENT_SECRET") or None,
    )
