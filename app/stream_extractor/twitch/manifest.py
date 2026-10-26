import re

import requests

from twitch.errors import TwitchError

RE_PLAYBACK_ACCESS_TOKEN = re.compile(r"^(\d+)p(\d+)?$")
RE_RESOLUTION = re.compile(r"RESOLUTION=(\d+)x(\d+)")
RE_RES_VALUE = re.compile(r"^(\d+)x(\d+)$")
RE_FRAME_RATE = re.compile(r"FRAME-RATE=([\d.]+)")
RE_ATTR = re.compile(r'([A-Z-]+)=("[^"]*"|[^,]*)')

NAME_ATTRS = ("VIDEO", "STABLE-VARIANT-ID", "IVS-NAME", "NAME", "GROUP-ID")


def _attrs(line):
    return {
        key: value.strip('"')
        for key, value in RE_ATTR.findall(line)
    }


def _stream_name(info_attrs, group_id):
    for key in NAME_ATTRS:
        value = info_attrs.get(key)
        if value:
            return value
    if group_id:
        return group_id

    res = RE_RES_VALUE.match(info_attrs.get("RESOLUTION", ""))
    if res:
        fps = info_attrs.get("FRAME-RATE") or "30"
        try:
            fps_int = int(float(fps.split(".")[0]))
        except ValueError:
            fps_int = 30
        return f"{res.group(2)}p{fps_int}"

    return "unknown"


def _absolutize(url, base_url):
    if url.startswith(("http://", "https://")):
        return url
    return base_url + url.lstrip("/")


def parse_master_m3u8(m3u8_url):
    try:
        resp = requests.get(
            m3u8_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 404:
            raise TwitchError("Twitch no tiene un manifiesto para esa URL.") from exc
        if status == 403:
            raise TwitchError("Manifiesto restringido por Twitch (403).") from exc
        raise TwitchError(f"Twitch devolvió un error HTTP {status}.") from exc
    except requests.RequestException as exc:
        raise TwitchError(
            f"No se pudo contactar con Twitch: {exc.__class__.__name__}."
        ) from exc

    base_url = m3u8_url.split("?")[0].rsplit("/", 1)[0] + "/"

    streams = {}
    group_id = None
    pending = None

    for raw in resp.text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#EXT-X-MEDIA"):
            group_id = _attrs(line).get("GROUP-ID") or group_id
            continue

        if line.startswith("#EXT-X-STREAM-INF"):
            pending = _stream_name(_attrs(line), group_id)
            group_id = None
            continue

        if line.startswith("#"):
            continue

        if pending:
            streams[pending] = {"url": _absolutize(line, base_url)}
            pending = None

    return streams


def quality_score(name):
    if name == "audio_only":
        return 0

    match = RE_PLAYBACK_ACCESS_TOKEN.match(name)
    if match:
        return int(match.group(1)) * 1000 + int(match.group(2) or 30)

    match = RE_RESOLUTION.search(name)
    if match:
        fps = 30
        res = RE_FRAME_RATE.search(name)
        if res:
            fps = int(float(res.group(1)))
        return int(match.group(2)) * 1000 + fps

    return 0
