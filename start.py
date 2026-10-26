#!/usr/bin/env python3
"""Run the public gateway and its private application workers."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTRACTOR_DIR = ROOT / "app" / "stream_extractor"
shutdown_signal: int | None = None


def request_shutdown(signum: int, _frame) -> None:
    global shutdown_signal
    shutdown_signal = signum


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 10
    for process in processes:
        if process.poll() is None:
            remaining = max(0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    env = os.environ.copy()
    env["FLASK_DEBUG"] = "0"
    env.setdefault("EXTRACTOR_WORKERS", "2")
    env.setdefault("LIVEPROXY_PORT", "53422")
    processes: list[subprocess.Popen] = []
    commands = [
        (
            ["liveproxy", "--host", "127.0.0.1", "--port", env["LIVEPROXY_PORT"]],
            ROOT,
            env,
        ),
        (
            [
                "gunicorn",
                "--bind",
                "127.0.0.1:5000",
                "--workers",
                env["EXTRACTOR_WORKERS"],
                "--timeout",
                "60",
                "app:app",
            ],
            EXTRACTOR_DIR,
            env,
        ),
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                env.get("PORT", "8000"),
                "--proxy-headers",
                "--forwarded-allow-ips",
                env.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
            ],
            ROOT,
            env,
        ),
    ]

    try:
        for command, cwd, process_env in commands:
            processes.append(subprocess.Popen(command, cwd=cwd, env=process_env))

        while shutdown_signal is None:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(
                        f"Application process {process.args[0]} exited with status {code}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return code or 1
            time.sleep(0.25)
        return 128 + shutdown_signal
    except OSError as exc:
        print(f"Could not start application process: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
