"""Playlist storage and M3U parsing/rendering."""
from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .config import get_settings
from twitch import TwitchError, parse_twitch_url

CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{4,25}$")
PLAYLIST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
URL_RE = re.compile(r"^https?://\S+$")
EXTINF_RE = re.compile(r"^#EXTINF:[^,]*,(.*)$")
LEGACY_PROXY_RE = re.compile(r"/base64/([^/]+)/?$")
LEGACY_COMMAND_RE = re.compile(
    r"^streamlink https?://(?:www\.)?twitch\.tv/([A-Za-z0-9_]{1,25}) best$",
    re.IGNORECASE,
)

_lock = threading.RLock()


class M3UError(Exception):
    status_code = 400


class InvalidInput(M3UError):
    status_code = 422


class NotFound(M3UError):
    status_code = 404


class Conflict(M3UError):
    status_code = 409


class PayloadTooLarge(M3UError):
    status_code = 413


class StorageError(M3UError):
    status_code = 500


@dataclass(frozen=True)
class Entry:
    name: str
    url: str | None
    channel: str | None = None

    @property
    def managed(self) -> bool:
        return self.channel is not None


@dataclass(frozen=True)
class PlaylistInfo:
    name: str
    count: int


def normalize_channel(raw: str | None) -> str:
    name = (raw or "").strip()
    try:
        is_live, channel = parse_twitch_url(name)
    except TwitchError as exc:
        raise InvalidInput(str(exc)) from exc
    if not is_live or not CHANNEL_RE.fullmatch(name):
        raise InvalidInput("Indica un nombre de canal de Twitch valido")
    return name


def normalize_playlist_name(raw: str) -> str:
    if not PLAYLIST_RE.fullmatch(raw or ""):
        raise InvalidInput(
            "Nombre de lista no valido. Usa letras, numeros, '.', '_' o '-' (maximo 64 caracteres)"
        )
    return raw


def parse_channel_names(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        items: list[str] = []
    elif isinstance(value, str):
        items = re.split(r"[,\s]+", value)
    else:
        items = [part for item in value for part in re.split(r"[,\s]+", item or "")]

    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        name = normalize_channel(item)
        if name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
    return names


def _legacy_channel(url: str) -> str | None:
    match = LEGACY_PROXY_RE.search(url)
    if not match:
        return None
    try:
        command = base64.b64decode(match.group(1), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    command_match = LEGACY_COMMAND_RE.fullmatch(command)
    if not command_match:
        return None
    try:
        return normalize_channel(command_match.group(1))
    except InvalidInput:
        return None


def parse_m3u(text: str) -> list[Entry]:
    entries: list[Entry] = []
    name: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = EXTINF_RE.match(line)
        if match:
            name = match.group(1).strip() or None
            continue
        if line.startswith("#"):
            continue
        if name and URL_RE.fullmatch(line):
            channel = _legacy_channel(line)
            if channel:
                entries.append(Entry(name=name, url=None, channel=channel))
            elif not LEGACY_PROXY_RE.search(line):
                entries.append(Entry(name=name, url=line))
        name = None
    return sort_entries(entries)


def sort_entries(entries: Iterable[Entry]) -> list[Entry]:
    unique: dict[str, Entry] = {}
    for entry in entries:
        key = (
            f"channel:{entry.channel.casefold()}"
            if entry.channel
            else f"static:{entry.name.casefold()}:{entry.url}"
        )
        unique.setdefault(key, entry)
    return sorted(unique.values(), key=lambda entry: entry.name.casefold())


def render_m3u(entries: Iterable[Entry]) -> str:
    lines = ["#EXTM3U"]
    for entry in sort_entries(entries):
        if not entry.url:
            raise InvalidInput(f"No hay URL resuelta para '{entry.name}'")
        lines.extend((f"#EXTINF:-1,{entry.name}", entry.url))
    return "\n".join(lines) + "\n"


def _path(name: str) -> Path:
    normalize_playlist_name(name)
    return get_settings().data_dir / f"{name}.json"


def write_playlist_file(path: Path, entries: Iterable[Entry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "entries": [asdict(entry) for entry in sort_entries(entries)],
    }
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_playlist(path: Path) -> list[Entry]:
    try:
        payload = json.loads(path.read_text("utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("entries"), list):
            raise ValueError("unsupported playlist format")
        entries = []
        for item in payload["entries"]:
            name = item["name"]
            url = item.get("url")
            channel = item.get("channel")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("invalid entry name")
            if channel is not None:
                channel = normalize_channel(channel)
                if url is not None:
                    raise ValueError("managed entry unexpectedly has a stored URL")
            elif not isinstance(url, str) or not URL_RE.fullmatch(url):
                raise ValueError("invalid static URL")
            entries.append(Entry(name=name, url=url, channel=channel))
        return sort_entries(entries)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, InvalidInput) as exc:
        raise StorageError(f"No se pudo leer la lista '{path.stem}': {exc}") from exc


def list_playlists() -> list[PlaylistInfo]:
    data_dir = get_settings().data_dir
    if not data_dir.is_dir():
        return []
    result = []
    for path in sorted(data_dir.glob("*.json"), key=lambda item: item.stem.casefold()):
        if PLAYLIST_RE.fullmatch(path.stem):
            result.append(PlaylistInfo(path.stem, len(_read_playlist(path))))
    return result


def load_playlist(name: str) -> list[Entry]:
    path = _path(name)
    if not path.is_file():
        raise NotFound(f"La lista '{name}' no existe")
    return _read_playlist(path)


def playlist_exists(name: str) -> bool:
    return _path(name).is_file()


def create_playlist(
    name: str, channels: str | Iterable[str] | None, *, overwrite: bool = False
) -> list[Entry]:
    path = _path(name)
    entries = [Entry(name=channel, url=None, channel=channel) for channel in parse_channel_names(channels)]
    with _lock:
        if path.exists() and not overwrite:
            raise Conflict(f"La lista '{name}' ya existe")
        write_playlist_file(path, entries)
    return sort_entries(entries)


def import_playlist(name: str, text: str) -> list[Entry]:
    path = _path(name)
    entries = parse_m3u(text)
    if not entries:
        raise InvalidInput("No se encontraron entradas M3U validas")
    with _lock:
        write_playlist_file(path, entries)
    return entries


def delete_playlist(name: str) -> None:
    path = _path(name)
    with _lock:
        if not path.is_file():
            raise NotFound(f"La lista '{name}' no existe")
        path.unlink()


def add_channels(name: str, channels: str | Iterable[str]) -> tuple[list[str], list[str], list[Entry]]:
    names = parse_channel_names(channels)
    if not names:
        raise InvalidInput("Indica al menos un canal")
    path = _path(name)
    with _lock:
        current = load_playlist(name)
        existing = {
            (entry.channel or entry.name).casefold()
            for entry in current
        }
        added: list[str] = []
        skipped: list[str] = []
        for channel in names:
            if channel.casefold() in existing:
                skipped.append(channel)
                continue
            current.append(Entry(name=channel, url=None, channel=channel))
            existing.add(channel.casefold())
            added.append(channel)
        if added:
            write_playlist_file(path, current)
        return added, skipped, sort_entries(current)


def remove_channel(name: str, channel: str) -> list[Entry]:
    path = _path(name)
    with _lock:
        current = load_playlist(name)
        target = (channel or "").strip().casefold()
        remaining = [
            entry
            for entry in current
            if entry.name.casefold() != target
            and (entry.channel or "").casefold() != target
        ]
        if len(remaining) == len(current):
            raise NotFound(f"El canal '{channel}' no esta en la lista")
        write_playlist_file(path, remaining)
    return sort_entries(remaining)
