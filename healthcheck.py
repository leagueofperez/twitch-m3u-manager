#!/usr/bin/env python3
"""Container healthcheck: verifies the app answers on /health.

The slim Python image ships neither curl nor wget, so the check reuses the
interpreter that is already there.
"""
from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 3


def check(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                print(f"unhealthy: {url} returned {response.status}")
                return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f"unhealthy: {url} failed: {exc}")
        return 1
    return 0


def check_internal_services() -> int:
    for name, internal_port in (
        ("Stream Extractor", 5000),
        ("LiveProxy", int(os.environ.get("LIVEPROXY_PORT", "53422"))),
    ):
        try:
            with socket.create_connection(("127.0.0.1", internal_port), timeout=3):
                pass
        except OSError as exc:
            print(f"unhealthy: {name} internal service failed: {exc}")
            return 1
    return 0


def main() -> int:
    port = os.environ.get("PORT", "8000")
    if check(f"http://127.0.0.1:{port}/health"):
        return 1
    return check_internal_services()


if __name__ == "__main__":
    sys.exit(main())
