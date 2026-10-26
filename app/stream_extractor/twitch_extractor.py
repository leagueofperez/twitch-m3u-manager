"""Backward-compatible public imports for the Twitch extraction modules."""

from twitch import (
    TwitchError,
    extract_streams_for_target,
    extract_streams_from_url,
    parse_master_m3u8,
    parse_twitch_url,
    quality_score,
)

__all__ = [
    "TwitchError",
    "extract_streams_for_target",
    "extract_streams_from_url",
    "parse_master_m3u8",
    "parse_twitch_url",
    "quality_score",
]
