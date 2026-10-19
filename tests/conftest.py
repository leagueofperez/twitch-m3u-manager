from fastapi.testclient import TestClient
import pytest

from app.auth_store import create_api_key
from app.config import get_settings


@pytest.fixture(autouse=True)
def twitch_credentials(monkeypatch):
    from twitch import client as twitch_client

    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "test-client-secret")
    twitch_client._app_access_token = None
    twitch_client._app_access_token_expires_at = 0
    twitch_client._app_access_token_credentials = None
    twitch_client._live_status_cache.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITCH_M3U_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TWITCH_M3U_COOKIE_SECURE", "false")
    monkeypatch.setenv("TWITCH_M3U_LOGIN_USERNAME", "test-admin")
    monkeypatch.setenv("TWITCH_M3U_LOGIN_PASSWORD", "test-password-long-enough")
    monkeypatch.setattr(
        "app.routers.api.check_channels_live",
        lambda channels: {channel.casefold(): True for channel in channels},
    )
    from app.main import app

    with TestClient(app) as test_client:
        _key, plaintext = create_api_key(
            get_settings().auth_db_path, "test-admin", "read-write"
        )
        test_client.headers["X-API-Key"] = plaintext
        yield test_client
