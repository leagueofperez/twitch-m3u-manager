"""Resolve managed Twitch entries only when generating a downloadable playlist."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import m3u
from twitch import (
    ChannelNotFound,
    ChannelOffline,
    TwitchError,
    TwitchRateLimited,
    check_live_channels,
    extract_streams_for_target,
    quality_score,
)

_MAX_CONCURRENT_EXTRACTIONS = 4


class ExtractionFailed(m3u.M3UError):
    status_code = 502


class LiveCheckFailed(m3u.M3UError):
    status_code = 502


class UpstreamRateLimited(m3u.M3UError):
    status_code = 429

    def __init__(self, retry_after: str | None = None):
        super().__init__("Twitch is rate limiting requests. Please retry later.")
        self.retry_after = retry_after


def check_playlist_channels(entries: list[m3u.Entry]) -> dict[str, bool]:
    channels = list(dict.fromkeys(
        entry.channel.casefold()
        for entry in entries
        if entry.channel
    ))
    return check_channels_live(channels)


def check_channels_live(channels: list[str]) -> dict[str, bool]:
    if not channels:
        return {}
    try:
        return check_live_channels(channels)
    except TwitchRateLimited as exc:
        raise UpstreamRateLimited(exc.retry_after) from exc
    except TwitchError as exc:
        raise LiveCheckFailed(f"No se pudo comprobar el estado de los canales: {exc}") from exc


def resolve_entries(entries: list[m3u.Entry]) -> list[m3u.Entry]:
    resolved: list[m3u.Entry | None] = [None] * len(entries)
    failures: list[str] = []
    live_status = check_playlist_channels(entries)
    pending: list[tuple[int, m3u.Entry]] = []
    for index, entry in enumerate(entries):
        if not entry.channel:
            resolved[index] = entry
            continue
        if live_status.get(entry.channel.casefold(), False):
            pending.append((index, entry))

    def extract(entry: m3u.Entry) -> tuple[m3u.Entry | None, str | None]:
        try:
            streams = extract_streams_for_target(True, entry.channel, known_live=True)
            if not streams:
                raise TwitchError("Twitch no devolvio streams.")
            stream = max(streams, key=lambda item: quality_score(item["quality"]))
            return m3u.Entry(name=entry.name, url=stream["url"]), None
        except (ChannelOffline, ChannelNotFound):
            return None, None
        except TwitchRateLimited as exc:
            raise UpstreamRateLimited(exc.retry_after) from exc
        except TwitchError as exc:
            return None, f"{entry.channel} ({exc})"

    if pending:
        with ThreadPoolExecutor(
            max_workers=min(_MAX_CONCURRENT_EXTRACTIONS, len(pending))
        ) as executor:
            results = executor.map(extract, (entry for _, entry in pending))
            for (index, _), (resolved_entry, failure) in zip(pending, results):
                resolved[index] = resolved_entry
                if failure:
                    failures.append(failure)

    if failures:
        failed = ", ".join(failures)
        raise ExtractionFailed(f"No se pudo extraer el stream de: {failed}")
    return [entry for entry in resolved if entry is not None]


def render_playlist(entries: list[m3u.Entry]) -> str:
    return m3u.render_m3u(resolve_entries(entries))
