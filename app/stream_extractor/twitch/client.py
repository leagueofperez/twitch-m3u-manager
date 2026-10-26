import random
from urllib.parse import urlencode

import requests

from twitch.errors import TwitchError

CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
GQL_URL = "https://gql.twitch.tv/gql"
USHER_URL = "https://usher.ttvnw.net"
SUPPORTED_CODECS = "h264"

HASH_TOKEN = "ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9"
HASH_CHANNEL_SHELL = "fea4573a7bf2644f5b3f2cbbdcbee0d17312e48d2e55f080589d053aad353f11"
HASH_STREAM_METADATA = "b57f9b910f8cd1a4659d894fe7550ccc81ec9052c01e438b290fd66a040b9b93"


def _gql(queries):
    batched = isinstance(queries, list)
    payload = queries if batched else [queries]
    headers = {"Client-ID": CLIENT_ID, "User-Agent": "Mozilla/5.0"}
    resp = requests.post(GQL_URL, json=payload, headers=headers, timeout=25)
    resp.raise_for_status()
    data = resp.json()
    return data if batched else (data[0] if data else {})


def _persisted_query(operation, sha256, **variables):
    return {
        "operationName": operation,
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha256}},
        "variables": variables,
    }


def fetch_playback_token(channel_or_id, is_live=True):
    """Return the playback token, signature, and optional live-channel status."""
    queries = []
    if is_live:
        queries.append(
            _persisted_query("ChannelShell", HASH_CHANNEL_SHELL, login=channel_or_id)
        )
        queries.append(
            _persisted_query(
                "StreamMetadata",
                HASH_STREAM_METADATA,
                channelLogin=channel_or_id,
                includeIsDJ=True,
            )
        )

    token_slot = len(queries)
    queries.append(
        _persisted_query(
            "PlaybackAccessToken",
            HASH_TOKEN,
            isLive=is_live,
            login=channel_or_id if is_live else "",
            isVod=not is_live,
            vodID=channel_or_id if not is_live else "",
            playerType="embed",
            platform="site",
        )
    )

    try:
        data = _gql(queries)
    except requests.RequestException as exc:
        raise TwitchError(
            f"No se pudo contactar con Twitch: {exc.__class__.__name__}."
        ) from exc

    reason = None
    if is_live:
        shell = data[0].get("data") or {}
        metadata = data[1].get("data") or {}
        user_or_error = shell.get("userOrError") or {}
        user = metadata.get("user")
        if user_or_error.get("__typename") == "UserNotFound" or user is None:
            reason = "notfound"
        elif user.get("stream") is None:
            reason = "offline"

    entry = data[token_slot]
    key = "streamPlaybackAccessToken" if is_live else "videoPlaybackAccessToken"
    token_obj = (entry.get("data") or {}).get(key)

    if not token_obj:
        if reason == "notfound":
            raise TwitchError(f"El canal '{channel_or_id}' no existe.")
        if reason == "offline":
            raise TwitchError(f"El canal '{channel_or_id}' está offline.")
        if entry.get("errors"):
            raise TwitchError("Twitch rechazó la consulta de token de reproducción.")
        if is_live:
            raise TwitchError(
                "Twitch no devolvió un token de reproducción para ese canal."
            )
        raise TwitchError(
            "No se pudo reproducir ese VOD. Puede estar eliminado, ser privado, "
            "tener restricción de edad o de suscripción."
        )

    return token_obj["value"], token_obj["signature"], reason


def build_usher_url(channel_or_id, token, sig, is_live=True):
    params = {
        "platform": "web",
        "p": random.randint(0, 999999),
        "allow_source": "true",
        "allow_audio_only": "true",
        "playlist_include_framerate": "true",
        "multigroup_video": "true",
        "supported_codecs": SUPPORTED_CODECS,
    }

    if is_live:
        path = f"/api/v2/channel/hls/{channel_or_id.lower()}.m3u8"
        params["sig"] = sig
        params["token"] = token
        params["fast_bread"] = "true"
    else:
        path = f"/vod/v2/{channel_or_id}.m3u8"
        params["nauthsig"] = sig
        params["nauth"] = token

    return f"{USHER_URL}{path}?{urlencode(params)}"
