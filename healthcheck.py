#!/usr/bin/env python3
"""Container healthcheck: verifies the app answers on /health.

The slim Python image ships neither curl nor wget, so the check reuses the
interpreter that is already there.
"""
from __future__ import annotations

import os
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


def main() -> int:
    port = os.environ.get("PORT", "8000")
    return check(f"http://127.0.0.1:{port}/health")


if __name__ == "__main__":
    sys.exit(main())
