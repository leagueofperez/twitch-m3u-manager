import random
import time
import threading
from urllib.parse import urlencode

import requests

from twitch.errors import ChannelNotFound, ChannelOffline, TwitchError, TwitchRateLimited

CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
GQL_URL = "https://gql.twitch.tv/gql"
USHER_URL = "https://usher.ttvnw.net"
SUPPORTED_CODECS = "h264"

HASH_TOKEN = "ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9"
HASH_CHANNEL_SHELL = "fea4573a7bf2644f5b3f2cbbdcbee0d17312e48d2e55f080589d053aad353f11"
HASH_STREAM_METADATA = "b57f9b910f8cd1a4659d894fe7550ccc81ec9052c01e438b290fd66a040b9b93"
LIVE_STATUS_CACHE_TTL = 20
_live_status_cache = {}
_live_status_lock = threading.Lock()


def _gql(queries):
    batched = isinstance(queries, list)
    payload = queries if batched else [queries]
    headers = {"Client-ID": CLIENT_ID, "User-Agent": "Mozilla/5.0"}
    resp = requests.post(GQL_URL, json=payload, headers=headers, timeout=25)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if resp.status_code == 429:
            raise TwitchRateLimited(resp.headers.get("Retry-After")) from exc
        raise
    data = resp.json()
    return data if batched else (data[0] if data else {})


def _persisted_query(operation, sha256, **variables):
    return {
        "operationName": operation,
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": sha256}},
        "variables": variables,
    }


def _raise_graphql_errors(response):
    errors = response.get("errors") or []
    for error in errors:
        if not isinstance(error, dict):
            continue
        extensions = error.get("extensions") or {}
        if not isinstance(extensions, dict):
            extensions = {}
        code = str(extensions.get("code") or "").upper()
        message = str(error.get("message") or "")
        if code in {"THROTTLED", "RATE_LIMITED", "TOO_MANY_REQUESTS"} or "rate limit" in message.lower():
            retry_after = extensions.get("retryAfter") or extensions.get("retry_after")
            raise TwitchRateLimited(str(retry_after) if retry_after is not None else None)
    return bool(errors)


def check_live_channels(channels):
    """Return live status for channels using cached, batched Twitch queries."""
    unique = sorted(set(channel.casefold() for channel in channels))
    if not unique:
        return {}

    now = time.monotonic()
    statuses = {}
    uncached = []
    with _live_status_lock:
        for channel in unique:
            cached = _live_status_cache.get(channel)
            if cached and cached[0] > now:
                statuses[channel] = cached[1]
            else:
                uncached.append(channel)

    for start in range(0, len(uncached), 5):
        batch = uncached[start:start + 5]
        queries = []
        for channel in batch:
            queries.append(
                _persisted_query(
                    "StreamMetadata",
                    HASH_STREAM_METADATA,
                    channelLogin=channel,
                    includeIsDJ=True,
                )
            )

        try:
            data = _gql(queries)
        except TwitchRateLimited:
            raise
        except requests.RequestException as exc:
            raise TwitchError(
                f"No se pudo contactar con Twitch: {exc.__class__.__name__}."
            ) from exc
        if not isinstance(data, list) or len(data) != len(queries):
            raise TwitchError("Twitch devolvió una respuesta incompleta al comprobar canales.")

        for index, channel in enumerate(batch):
            metadata_response = data[index]
            if not isinstance(metadata_response, dict):
                raise TwitchError(f"Twitch devolvió un estado inválido para '{channel}'.")
            if _raise_graphql_errors(metadata_response):
                raise TwitchError(f"No se pudo comprobar el estado de '{channel}'.")
            metadata = metadata_response.get("data") or {}
            if not isinstance(metadata, dict):
                raise TwitchError(f"Twitch devolvió un estado inválido para '{channel}'.")
            user = metadata.get("user")
            if user is None:
                statuses[channel] = False
                continue
            if not isinstance(user, dict):
                raise TwitchError(f"Twitch no devolvió el estado de '{channel}'.")
            statuses[channel] = user.get("stream") is not None

    expires_at = time.monotonic() + LIVE_STATUS_CACHE_TTL
    with _live_status_lock:
        for channel, is_live in statuses.items():
            _live_status_cache[channel] = (expires_at, is_live)
        for key, (expires_at, _) in list(_live_status_cache.items()):
            if expires_at <= time.monotonic():
                _live_status_cache.pop(key, None)
        if len(_live_status_cache) > 128:
            oldest = sorted(_live_status_cache.items(), key=lambda item: item[1][0])
            for key, _ in oldest[:len(_live_status_cache) - 128]:
                _live_status_cache.pop(key, None)
    return statuses


def fetch_playback_token(channel_or_id, is_live=True, known_live=False):
    """Return the playback token, signature, and optional live-channel status."""
    queries = []
    if is_live and not known_live:
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
    if is_live and not known_live:
        shell = data[0].get("data") or {}
        metadata = data[1].get("data") or {}
        user_or_error = shell.get("userOrError") or {}
        user = metadata.get("user")
        if user_or_error.get("__typename") == "UserNotFound":
            reason = "notfound"
        elif user is None:
            raise TwitchError(f"Twitch no devolvió el estado de '{channel_or_id}'.")
        elif user.get("stream") is None:
            reason = "offline"

    entry = data[token_slot]
    key = "streamPlaybackAccessToken" if is_live else "videoPlaybackAccessToken"
    if _raise_graphql_errors(entry):
        if is_live:
            raise TwitchError("Twitch rechazó la consulta de token de reproducción.")
        raise TwitchError("Twitch rechazó la consulta de token de VOD.")
    token_obj = (entry.get("data") or {}).get(key)

    if not token_obj:
        if reason == "notfound":
            raise ChannelNotFound(f"El canal '{channel_or_id}' no existe.")
        if reason == "offline":
            raise ChannelOffline(f"El canal '{channel_or_id}' está offline.")
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
