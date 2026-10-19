import requests
import pytest

from twitch import TwitchError, check_live_channels
from twitch.client import _live_status_cache, fetch_playback_token
from twitch.errors import TwitchRateLimited


def test_check_live_channels_batches_status_queries(monkeypatch):
    calls = []

    def gql(queries):
        calls.append(queries)
        responses = []
        for query in queries:
            channel = query["variables"]["channelLogin"]
            if channel == "missing":
                responses.append({"data": {"user": None}})
            else:
                stream = {"id": "123"} if channel == "live" else None
                responses.append({"data": {"user": {"stream": stream}}})
        return responses

    monkeypatch.setattr("twitch.client._gql", gql)
    channels = ["live", "offline", "missing"] + [f"channel{i}" for i in range(8)]

    result = check_live_channels(channels)

    assert result["live"] is True
    assert result["offline"] is False
    assert result["missing"] is False
    assert len(calls) == 3
    assert [len(call) for call in calls] == [5, 5, 1]


def test_check_live_channels_caches_recent_result(monkeypatch):
    _live_status_cache.clear()
    calls = []

    def gql(queries):
        calls.append(queries)
        return [{"data": {"user": {"stream": {"id": "123"}}}} for _query in queries]

    monkeypatch.setattr("twitch.client._gql", gql)

    assert check_live_channels(["live", "other"]) == {"live": True, "other": True}
    assert check_live_channels(["other", "live"]) == {"live": True, "other": True}
    assert len(calls) == 1

    assert check_live_channels(["live", "new-channel"]) == {
        "live": True,
        "new-channel": True,
    }
    assert len(calls) == 2


def test_check_live_channels_preserves_twitch_retry_after(monkeypatch):
    _live_status_cache.pop(("rate-limited-channel",), None)
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "45"
    error = requests.HTTPError(response=response)

    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "45"}

        def raise_for_status(self):
            raise error

    monkeypatch.setattr("twitch.client.requests.post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(TwitchRateLimited) as exc:
        check_live_channels(["rate-limited-channel"])
    assert exc.value.retry_after == "45"


def test_check_live_channels_detects_graphql_throttling(monkeypatch):
    _live_status_cache.pop(("graphql-throttled",), None)
    monkeypatch.setattr(
        "twitch.client._gql",
        lambda _queries: [
            {
                "errors": [
                    {
                        "message": "Request rate limit exceeded",
                        "extensions": {"code": "THROTTLED", "retryAfter": 30},
                    }
                ]
            }
        ],
    )

    with pytest.raises(TwitchRateLimited) as exc:
        check_live_channels(["graphql-throttled"])
    assert exc.value.retry_after == "30"


def test_check_live_channels_raises_on_incomplete_twitch_response(monkeypatch):
    _live_status_cache.pop("live", None)
    monkeypatch.setattr("twitch.client._gql", lambda _queries: [])

    with pytest.raises(TwitchError, match="respuesta incompleta"):
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
