from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITCH_M3U_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TWITCH_M3U_AUTH_USER", raising=False)
    monkeypatch.delenv("TWITCH_M3U_AUTH_PASSWORD", raising=False)
    monkeypatch.setattr(
        "app.routers.api.check_channels_live",
        lambda channels: {channel.casefold(): True for channel in channels},
    )
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
