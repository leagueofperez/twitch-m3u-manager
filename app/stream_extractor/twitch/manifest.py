import re
from urllib.parse import urljoin

import requests

from twitch.errors import TwitchError

RE_PLAYBACK_ACCESS_TOKEN = re.compile(r"^(\d+)p(\d+)?$")
RE_RESOLUTION = re.compile(r"RESOLUTION=(\d+)x(\d+)")
RE_RES_VALUE = re.compile(r"^(\d+)x(\d+)$")
RE_FRAME_RATE = re.compile(r"FRAME-RATE=([\d.]+)")
RE_ATTR = re.compile(r'([A-Z-]+)=("[^"]*"|[^,]*)')

NAME_ATTRS = ("STABLE-VARIANT-ID", "IVS-NAME", "NAME")


def _attrs(line):
    return {
        key: value.strip('"')
        for key, value in RE_ATTR.findall(line)
    }


def _stream_name(info_attrs, video_groups):
    for key in NAME_ATTRS:
        value = info_attrs.get(key)
        if value:
            return value

    video_group = info_attrs.get("VIDEO")
    if video_group and video_group in video_groups:
        return video_groups[video_group]

    res = RE_RES_VALUE.match(info_attrs.get("RESOLUTION", ""))
    if res:
        fps = info_attrs.get("FRAME-RATE") or "30"
        try:
            fps_int = int(float(fps.split(".")[0]))
        except ValueError:
            fps_int = 30
        return f"{res.group(2)}p{fps_int}"

    return video_group or "unknown"


def _absolutize(url, base_url):
    return urljoin(base_url, url)


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

    video_groups = {}
    lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
    for line in lines:
        if not line.startswith("#EXT-X-MEDIA"):
            continue
        attrs = _attrs(line)
        if attrs.get("TYPE") != "VIDEO" or not attrs.get("GROUP-ID") or not attrs.get("NAME"):
            continue
        group_id = attrs["GROUP-ID"]
        if attrs.get("DEFAULT", "NO").upper() == "YES":
            video_groups[group_id] = attrs["NAME"]
        else:
            video_groups.setdefault(group_id, attrs["NAME"])

    streams = {}
    pending = None

    for line in lines:
        if line.startswith("#EXT-X-STREAM-INF"):
            pending = _stream_name(_attrs(line), video_groups)
            continue

        if line.startswith("#"):
            continue

        if pending:
            streams[pending] = {"url": _absolutize(line, m3u8_url)}
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
