import base64

import pytest

from app import m3u
from app.extraction import ExtractionFailed, render_playlist
from twitch import TwitchError


def test_create_add_remove_and_list_playlists(client):
    response = client.post(
        "/api/playlists",
        json={"name": "demo", "channels": "zeta, Alfa beta"},
    )
    assert response.status_code == 201
    assert [entry["channel"] for entry in response.json()["channels"]] == [
        "Alfa",
        "beta",
        "zeta",
    ]
    assert all(entry["managed"] and entry["url"] is None for entry in response.json()["channels"])
    assert response.json()["channel_status"] == [
        {"channel": "zeta", "live": True},
        {"channel": "Alfa", "live": True},
        {"channel": "beta", "live": True},
    ]
    assert client.get("/api/playlists").json() == [
        {"name": "demo", "count": 3, "m3u": "/m3u/demo.m3u"}
    ]

    added = client.post(
        "/api/playlists/demo/channels",
        json={"channels": "carlos, BETA, anita"},
    ).json()
    assert added["added"] == ["carlos", "anita"]
    assert added["skipped"] == ["BETA"]
    assert client.delete("/api/playlists/demo/channels/Alfa").status_code == 200
    assert client.delete("/api/playlists/demo").status_code == 204
    assert client.get("/api/playlists/demo").status_code == 404


def test_create_playlist_checks_only_initial_channels(client, monkeypatch):
    checked = []

    def check(channels):
        checked.extend(channels)
        return {"live": True, "offline": False}

    monkeypatch.setattr("app.routers.api.check_channels_live", check)
    response = client.post(
        "/api/playlists",
        json={"name": "new-list", "channels": "live,offline"},
    )

    assert response.status_code == 201
    assert checked == ["live", "offline"]
    assert response.json()["channel_status"] == [
        {"channel": "live", "live": True},
        {"channel": "offline", "live": False},
    ]


def test_invalid_channel_and_playlist_names(client):
    assert client.post("/api/playlists", json={"name": "../bad"}).status_code == 422
    assert client.post(
        "/api/playlists",
        json={"name": "demo", "channels": "ibai; echo bad"},
    ).status_code == 422


def test_export_refreshes_and_selects_highest_quality(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo", "channels": "ibai"})
    calls = []

    monkeypatch.setattr("app.extraction.check_live_channels", lambda channels: {"ibai": True})

    def extract(is_live, channel, *, known_live):
        calls.append((is_live, channel))
        assert known_live is True
        return [
            {"quality": "720p60", "url": "https://cdn.test/720.m3u8"},
            {"quality": "1080p60", "url": "https://cdn.test/1080.m3u8"},
        ]

    monkeypatch.setattr("app.extraction.extract_streams_for_target", extract)
    response = client.get("/m3u/demo.m3u")

    assert response.status_code == 200
    assert "#EXTINF:-1,ibai\nhttps://cdn.test/1080.m3u8" in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert calls == [(True, "ibai")]
    assert "attachment" in client.get("/m3u/demo.m3u?download=true").headers["content-disposition"]
    assert calls == [(True, "ibai"), (True, "ibai")]


def test_export_checks_all_channels_and_only_extracts_live_channels(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo", "channels": "ibai, offline"})
    checks = []
    extracts = []
    events = []

    def check(channels):
        checks.append(channels)
        events.append("check")
        return {"ibai": True, "offline": False}

    def extract(is_live, channel, *, known_live):
        extracts.append((is_live, channel))
        assert known_live is True
        events.append("extract")
        return [{"quality": "720p", "url": "https://cdn.test/live.m3u8"}]

    monkeypatch.setattr("app.extraction.check_live_channels", check)
    monkeypatch.setattr("app.extraction.extract_streams_for_target", extract)
    response = client.get("/m3u/demo.m3u")

    assert response.status_code == 200
    assert checks == [["ibai", "offline"]]
    assert extracts == [(True, "ibai")]
    assert events == ["check", "extract"]
    assert "ibai" in response.text
    assert "offline" not in response.text


def test_export_fails_clearly_if_initial_live_check_fails(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo", "channels": "ibai"})

    def fail_check(_channels):
        raise TwitchError("Twitch unreachable")

    def unexpected_extract(*_args, **_kwargs):
        pytest.fail("URL extraction should not run when the initial check fails")

    monkeypatch.setattr("app.extraction.check_live_channels", fail_check)
    monkeypatch.setattr("app.extraction.extract_streams_for_target", unexpected_extract)
    response = client.get("/m3u/demo.m3u")

    assert response.status_code == 502
    assert "Twitch unreachable" in response.json()["detail"]
    assert not response.text.startswith("#EXTM3U")


def test_twitch_rate_limit_returns_429_and_retry_after(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo", "channels": "ibai"})

    def fail_check(_channels):
        from app.extraction import UpstreamRateLimited

        raise UpstreamRateLimited("45")

    monkeypatch.setattr("app.routers.api.check_channels_live", fail_check)
    response = client.post("/api/playlists/demo/channels", json={"channels": "other"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "45"
    assert "rate limiting" in response.json()["detail"]


def test_add_channel_checks_status_and_keeps_offline_channels(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo"})
    checked = []

    def check(channels):
        checked.extend(channels)
        return {"ibai": True, "offline": False}

    monkeypatch.setattr("app.routers.api.check_channels_live", check)
    response = client.post("/api/playlists/demo/channels", json={"channels": "ibai,offline"})

    assert response.status_code == 200
    assert response.json()["playlist"]["channel_status"] == [
        {"channel": "ibai", "live": True},
        {"channel": "offline", "live": False},
    ]
    assert response.json()["added"] == ["ibai", "offline"]
    assert checked == ["ibai", "offline"]
    assert [entry["channel"] for entry in response.json()["playlist"]["channels"]] == [
        "ibai",
        "offline",
    ]


def test_adding_existing_channels_does_not_check_twitch_again(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo", "channels": "ibai"})

    def fail_check(_channels):
        pytest.fail("Duplicate channels should not trigger another Twitch check")

    monkeypatch.setattr("app.routers.api.check_channels_live", fail_check)
    response = client.post("/api/playlists/demo/channels", json={"channels": "IBAI"})

    assert response.status_code == 200
    assert response.json()["added"] == []
    assert response.json()["skipped"] == ["IBAI"]


def test_import_keeps_direct_urls_and_migrates_legacy_twitch_commands(client):
    command = base64.b64encode(b"streamlink https://twitch.tv/ibai best").decode()
    unknown = base64.b64encode(b"not a twitch stream").decode()
    content = (
        "#EXTM3U\n"
        "#EXTINF:-1,Ibai\n"
        f"http://127.0.0.1:53422/base64/{command}/\n"
        "#EXTINF:-1,Static channel\n"
        "https://cdn.test/static.m3u8\n"
        "#EXTINF:-1,Unknown proxy\n"
        f"http://127.0.0.1:53422/base64/{unknown}/\n"
    )
    response = client.put(
        "/m3u/old.m3u",
        content=content,
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 200
    entries = response.json()["channels"]
    assert [entry["name"] for entry in entries] == ["Ibai", "Static channel"]
    assert entries[0]["channel"] == "ibai" and entries[0]["managed"]
    assert entries[1]["url"] == "https://cdn.test/static.m3u8"
    assert "base64/" not in (client.get("/api/playlists/old").text)


def test_m3u_import_limits_and_requires_supported_entries(client):
    assert client.put(
        "/m3u/empty.m3u",
        content="#EXTM3U\nunsupported",
        headers={"content-type": "text/plain"},
    ).status_code == 422
    assert client.put(
        "/m3u/large.m3u",
        content="x" * 1_000_001,
        headers={"content-type": "text/plain"},
    ).status_code == 413


def test_web_interface_has_no_legacy_proxy_or_generator_features(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo"})
    pytest_check_calls = []

    def fail_check(channels):
        pytest_check_calls.append(channels)
        raise AssertionError("Opening the playlist page must not check Twitch")

    monkeypatch.setattr("app.routers.api.check_channels_live", fail_check)
    home = client.get("/")
    playlist = client.get("/p/demo")

    assert home.status_code == playlist.status_code == 200
    assert "Twitch M3U Manager" in home.text
    assert "LiveProxy" not in home.text + playlist.text
    assert "Al añadir canales se comprueba si están en directo" in playlist.text
    assert "live-status" not in playlist.text
    assert pytest_check_calls == []
    assert client.get("/generator").status_code == 404
    assert client.post("/api/url", json={"channel": "ibai"}).status_code == 404
    assert client.get("/api/playlists/demo/live-status").status_code == 404


def test_optional_basic_auth_uses_new_project_settings(client, monkeypatch):
    client.post("/api/playlists", json={"name": "demo"})
    monkeypatch.setenv("TWITCH_M3U_AUTH_USER", "admin")
    monkeypatch.setenv("TWITCH_M3U_AUTH_PASSWORD", "secret")

    assert client.get("/api/playlists").status_code == 401
    assert client.get("/api/playlists", auth=("admin", "secret")).status_code == 200
    assert client.get("/health").status_code == 200


def test_migration_is_idempotent_and_retains_static_entries(tmp_path):
    from app.migration import migrate_legacy_playlists

    source = tmp_path / "old"
    target = tmp_path / "new"
    source.mkdir()
    command = base64.b64encode(b"streamlink https://twitch.tv/ibai best").decode()
    (source / "watch.m3u").write_text(
        "#EXTM3U\n"
        "#EXTINF:-1,Ibai\n"
        f"http://proxy.test/base64/{command}/\n"
        "#EXTINF:-1,Radio\n"
        "https://radio.test/live.m3u8\n",
        encoding="utf-8",
    )

    assert migrate_legacy_playlists(source, target) == {"watch": "migrated: 2 entries"}
    assert migrate_legacy_playlists(source, target) == {
        "watch": "skipped: destination already exists"
    }
    entries = m3u._read_playlist(target / "watch.json")
    assert [(entry.name, entry.channel, entry.url) for entry in entries] == [
        ("Ibai", "ibai", None),
        ("Radio", None, "https://radio.test/live.m3u8"),
    ]


def test_resolve_entries_reports_all_twitch_failures(monkeypatch):
    def extract(_is_live, channel, *, known_live):
        assert known_live is True
        if channel == "offline":
            raise TwitchError("offline")
        return [{"quality": "720p", "url": "https://cdn.test/live.m3u8"}]

    monkeypatch.setattr("app.extraction.extract_streams_for_target", extract)
    monkeypatch.setattr(
        "app.extraction.check_live_channels",
        lambda _channels: {"online": True, "offline": True},
    )
    entries = [
        m3u.Entry("online", None, "online"),
        m3u.Entry("offline", None, "offline"),
    ]
    with pytest.raises(ExtractionFailed, match="offline"):
        render_playlist(entries)
