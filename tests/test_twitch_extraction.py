from twitch.extraction import extract_streams_for_target


def test_live_stream_extraction_cache_is_short_lived_and_returns_copies(monkeypatch):
    from twitch import extraction

    extraction._live_stream_cache.clear()
    now = [100.0]
    calls = []

    def extract(is_live, target, *, known_live):
        calls.append((is_live, target, known_live))
        return [{"quality": "720p60", "url": f"https://cdn.test/{len(calls)}.m3u8"}]

    monkeypatch.setattr("twitch.extraction.time.monotonic", lambda: now[0])
    monkeypatch.setattr("twitch.extraction._extract_streams_for_target", extract)

    first = extract_streams_for_target(True, "Channel", known_live=True)
    first[0]["url"] = "mutated"
    second = extract_streams_for_target(True, "channel")

    assert second == [{"quality": "720p60", "url": "https://cdn.test/1.m3u8"}]
    assert calls == [(True, "Channel", True)]

    now[0] += extraction.LIVE_STREAM_CACHE_TTL
    refreshed = extract_streams_for_target(True, "channel")

    assert refreshed == [{"quality": "720p60", "url": "https://cdn.test/2.m3u8"}]
    assert len(calls) == 2
    extraction._live_stream_cache.clear()


def test_vod_extractions_are_not_cached(monkeypatch):
    calls = []

    def extract(is_live, target, *, known_live):
        calls.append((is_live, target, known_live))
        return [{"quality": "720p60", "url": "https://cdn.test/vod.m3u8"}]

    monkeypatch.setattr("twitch.extraction._extract_streams_for_target", extract)

    extract_streams_for_target(False, "123456789")
    extract_streams_for_target(False, "123456789")

    assert calls == [(False, "123456789", False)] * 2
