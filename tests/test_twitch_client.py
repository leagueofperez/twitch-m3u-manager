import requests
import pytest

from twitch import TwitchError, check_live_channels
from twitch.client import _live_status_cache, fetch_playback_token
from twitch.errors import TwitchRateLimited


class FakeResponse:
    def __init__(self, data, *, status_code=200, headers=None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def json(self):
        return self._data


def install_app_token(monkeypatch):
    calls = []

    def post(url, *, data, timeout):
        calls.append((url, data, timeout))
        return FakeResponse({"access_token": "app-token", "expires_in": 3600})

    monkeypatch.setattr("twitch.client.requests.post", post)
    return calls


def test_check_live_channels_uses_one_authenticated_helix_request(monkeypatch):
    token_calls = install_app_token(monkeypatch)
    calls = []

    def get(url, *, params, headers, timeout):
        calls.append((url, params, headers, timeout))
        return FakeResponse(
            {"data": [{"user_id": "1", "user_login": "live"}]}
        )

    monkeypatch.setattr("twitch.client.requests.get", get)
    channels = ["live", "offline", "missing"]

    result = check_live_channels(channels)

    assert result == {"live": True, "offline": False, "missing": False}
    assert len(token_calls) == 1
    assert token_calls[0][0] == "https://id.twitch.tv/oauth2/token"
    assert token_calls[0][1] == {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "grant_type": "client_credentials",
    }
    assert len(calls) == 1
    url, params, headers, timeout = calls[0]
    assert url == "https://api.twitch.tv/helix/streams"
    assert params == [("user_login", channel) for channel in sorted(channels)]
    assert headers == {
        "Client-ID": "test-client-id",
        "Authorization": "Bearer app-token",
    }
    assert timeout == 25


def test_check_live_channels_chunks_at_helix_filter_limit(monkeypatch):
    token_calls = install_app_token(monkeypatch)
    calls = []

    def get(_url, *, params, **_kwargs):
        calls.append(params)
        return FakeResponse({"data": []})

    monkeypatch.setattr("twitch.client.requests.get", get)
    channels = [f"channel{i:03}" for i in range(205)]

    result = check_live_channels(channels)

    assert result == {channel: False for channel in channels}
    assert [len(params) for params in calls] == [100, 100, 5]
    assert all(name == "user_login" for call in calls for name, _ in call)
    assert len(token_calls) == 1


def test_check_live_channels_caches_recent_result(monkeypatch):
    install_app_token(monkeypatch)
    calls = []

    def get(_url, *, params, **_kwargs):
        calls.append(params)
        return FakeResponse(
            {
                "data": [
                    {"user_id": str(i), "user_login": value}
                    for i, (_key, value) in enumerate(params)
                ]
            }
        )

    monkeypatch.setattr("twitch.client.requests.get", get)

    assert check_live_channels(["live", "other"]) == {"live": True, "other": True}
    monkeypatch.delenv("TWITCH_CLIENT_ID")
    monkeypatch.delenv("TWITCH_CLIENT_SECRET")
    assert check_live_channels(["other", "live"]) == {"live": True, "other": True}
    assert len(calls) == 1

    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "test-client-secret")
    assert check_live_channels(["live", "new-channel"]) == {
        "live": True,
        "new-channel": True,
    }
    assert len(calls) == 2


def test_check_live_channels_preserves_twitch_retry_after(monkeypatch):
    install_app_token(monkeypatch)
    monkeypatch.setattr(
        "twitch.client.requests.get",
        lambda *_args, **_kwargs: FakeResponse(
            {}, status_code=429, headers={"Retry-After": "45"}
        ),
    )

    with pytest.raises(TwitchRateLimited) as exc:
        check_live_channels(["rate-limited-channel"])
    assert exc.value.retry_after == "45"


def test_check_live_channels_raises_on_incomplete_twitch_response(monkeypatch):
    install_app_token(monkeypatch)
    monkeypatch.setattr(
        "twitch.client.requests.get",
        lambda *_args, **_kwargs: FakeResponse([]),
    )

    with pytest.raises(TwitchError, match="respuesta incompleta"):
        check_live_channels(["live"])


def test_check_live_channels_requires_app_credentials(monkeypatch):
    monkeypatch.delenv("TWITCH_CLIENT_ID")
    monkeypatch.delenv("TWITCH_CLIENT_SECRET")

    with pytest.raises(TwitchError, match="TWITCH_CLIENT_ID"):
        check_live_channels(["live"])


def test_fetch_playback_token_skips_status_queries_for_prechecked_live_channel(monkeypatch):
    calls = []

    def gql(queries):
        calls.extend(queries)
        return [
            {
                "data": {
                    "streamPlaybackAccessToken": {
                        "value": "playback-token",
                        "signature": "signature",
                    }
                }
            }
        ]

    monkeypatch.setattr("twitch.client._gql", gql)

    token, signature, reason = fetch_playback_token("live", known_live=True)

    assert (token, signature, reason) == ("playback-token", "signature", None)
    assert len(calls) == 1
    assert calls[0]["operationName"] == "PlaybackAccessToken"
