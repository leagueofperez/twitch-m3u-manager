#!/usr/bin/env python3
"""Migrate legacy sample playlists into the unified app's data directory."""
import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.config import get_settings
from app.migration import migrate_legacy_playlists


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    args = parser.parse_args()
    if not args.source_dir.is_dir():
        parser.error(f"source directory does not exist: {args.source_dir}")
    for playlist, result in migrate_legacy_playlists(
        args.source_dir, get_settings().data_dir
    ).items():
        print(f"{playlist}: {result}")
