"""Resolve managed Twitch entries only when generating a downloadable playlist."""
from __future__ import annotations

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
    resolved: list[m3u.Entry] = []
    failures: list[str] = []
    live_status = check_playlist_channels(entries)
    for entry in entries:
        if not entry.channel:
            resolved.append(entry)
            continue
        if not live_status.get(entry.channel.casefold(), False):
            continue
        try:
            streams = extract_streams_for_target(True, entry.channel, known_live=True)
            if not streams:
                raise TwitchError("Twitch no devolvio streams.")
            stream = max(streams, key=lambda item: quality_score(item["quality"]))
            resolved.append(m3u.Entry(name=entry.name, url=stream["url"]))
        except (ChannelOffline, ChannelNotFound):
            continue
        except TwitchRateLimited as exc:
            raise UpstreamRateLimited(exc.retry_after) from exc
        except TwitchError as exc:
            failures.append(f"{entry.channel} ({exc})")

    if failures:
        failed = ", ".join(failures)
        raise ExtractionFailed(f"No se pudo extraer el stream de: {failed}")
    return resolved


def render_playlist(entries: list[m3u.Entry]) -> str:
    return m3u.render_m3u(resolve_entries(entries))
