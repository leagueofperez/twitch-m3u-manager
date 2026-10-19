"""One-time conversion of legacy LiveProxy M3U files to managed playlists."""
from __future__ import annotations

from pathlib import Path

from . import m3u


def migrate_legacy_playlists(source_dir: Path, target_dir: Path) -> dict[str, str]:
    """Migrate playlists without overwriting any existing destination."""
    results: dict[str, str] = {}
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.glob("*.m3u"), key=lambda path: path.stem.casefold()):
        try:
            name = m3u.normalize_playlist_name(source.stem)
        except m3u.InvalidInput:
            results[source.name] = "skipped: invalid playlist name"
            continue
        destination = target_dir / f"{name}.json"
        if destination.exists():
            results[name] = "skipped: destination already exists"
            continue
        entries = m3u.parse_m3u(source.read_text("utf-8-sig", errors="replace"))
        if not entries:
            results[name] = "skipped: no supported M3U entries"
            continue
        m3u.write_playlist_file(destination, entries)
        results[name] = f"migrated: {len(entries)} entries"
    return results
