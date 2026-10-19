import requests

from twitch.client import build_usher_url, fetch_playback_token
from twitch.errors import ChannelNotFound, ChannelOffline, TwitchError
from twitch.manifest import parse_master_m3u8, quality_score
from twitch.urls import parse_twitch_url


def extract_streams_for_target(is_live, target, *, known_live=False):
    try:
        token, sig, reason = fetch_playback_token(
            target,
            is_live=is_live,
            known_live=known_live,
        )
        m3u8_url = build_usher_url(target, token, sig, is_live=is_live)
    except TwitchError:
        raise
    except requests.RequestException as exc:
        raise TwitchError(
            f"No se pudo contactar con Twitch: {exc.__class__.__name__}."
        ) from exc

    try:
        streams = parse_master_m3u8(m3u8_url)
    except TwitchError:
        if reason == "offline":
            raise ChannelOffline(f"El canal '{target}' está offline.") from None
        if reason == "notfound":
            raise ChannelNotFound(f"El canal '{target}' no existe.") from None
        raise
    except requests.RequestException as exc:
        raise TwitchError(
            f"No se pudo contactar con Twitch: {exc.__class__.__name__}."
        ) from exc

    if not streams:
        raise TwitchError(
            "No se encontraron streams. El canal podría haberse desconectado "
            "o la emisión tener restricciones de edad."
        )

    return [
        {"quality": quality, "url": info["url"]}
        for quality, info in sorted(
            streams.items(), key=lambda kv: quality_score(kv[0]), reverse=True
        )
    ]


def extract_streams_from_url(twitch_url):
    is_live, target = parse_twitch_url(twitch_url)
    return extract_streams_for_target(is_live, target)
