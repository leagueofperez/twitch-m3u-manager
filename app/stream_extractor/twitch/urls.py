import re
from urllib.parse import urlparse

from twitch.errors import TwitchError

RE_VOD = re.compile(r"/(?:[^/]+/)?v(?:ideos?)/(\d+)", re.IGNORECASE)
RE_CHANNEL = re.compile(r"^/([^/?#]+)/?$")
RE_CHANNEL_NAME = re.compile(r"^[A-Za-z0-9_]{4,25}$")
RE_BARE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
RE_BARE_VOD = re.compile(r"^\d{8,12}$")

BLOCKED_SEGMENTS = (
    "videos",
    "video",
    "directory",
    "settings",
    "downloads",
    "store",
    "subscriptions",
    "friends",
    "wallet",
    "drops",
    "following",
    "search",
    "popout",
    "moderator",
    "u",
    "p",
)


def _validate_channel(name):
    if not RE_CHANNEL_NAME.match(name):
        shown = name[:32] + ("…" if len(name) > 32 else "")
        raise TwitchError(
            f"'{shown}' no es un nombre de canal válido. "
            "Debe tener entre 4 y 25 caracteres (letras, números o _)."
        )
    return name.lower()


def _from_bare_token(raw):
    token = raw.strip("/")
    if RE_BARE_VOD.fullmatch(token):
        return False, token
    if RE_BARE_TOKEN.fullmatch(token):
        return True, _validate_channel(token)
    raise TwitchError(
        "Entrada no reconocida. Usa el nombre del canal (p. ej. admiralbulldog), "
        "un ID de VOD, o una URL completa de Twitch."
    )


def parse_twitch_url(url):
    raw = (url or "").strip()
    if not raw:
        raise TwitchError("URL vacía")

    if "://" not in raw and "." not in raw.split("/")[0]:
        return _from_bare_token(raw)

    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not (host == "twitch.tv" or host.endswith(".twitch.tv")):
        raise TwitchError("Solo se soportan URLs de Twitch.")

    path = parsed.path or "/"

    vod = RE_VOD.search(path)
    if vod:
        return False, vod.group(1)

    channel = RE_CHANNEL.match(path)
    if channel:
        name = channel.group(1)
        if name.lower() not in BLOCKED_SEGMENTS:
            return True, _validate_channel(name)

    raise TwitchError(
        "URL de Twitch no válida. Usa twitch.tv/<canal> o twitch.tv/videos/<id>."
    )
