"""Authenticated gateways to the internal Stream Extractor and LiveProxy."""
from __future__ import annotations

import base64
import binascii
import os
import re
from urllib.parse import quote

import requests
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

EXTRACTOR_URL = os.environ.get("EXTRACTOR_INTERNAL_URL", "http://127.0.0.1:5000")
EXTRACTOR_MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", "16384"))
LIVEPROXY_URL = os.environ.get(
    "LIVEPROXY_INTERNAL_URL",
    f"http://127.0.0.1:{os.environ.get('LIVEPROXY_PORT', '53422')}",
)
LIVEPROXY_COMMAND = re.compile(
    r"streamlink https://twitch\.tv/[A-Za-z0-9_]{1,25} best"
)
BASE64_PATH = re.compile(r"[A-Za-z0-9+/]+={0,2}")
REQUEST_HEADERS = ("accept", "content-type", "range", "if-range", "user-agent")
RESPONSE_HEADERS = (
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
)


def _response(upstream: requests.Response) -> StreamingResponse:
    headers = {
        name: upstream.headers[name]
        for name in RESPONSE_HEADERS
        if name in upstream.headers
    }
    return StreamingResponse(
        upstream.iter_content(chunk_size=64 * 1024),
        status_code=upstream.status_code,
        headers=headers,
        background=BackgroundTask(upstream.close),
    )


def _make_request(url: str, request: Request) -> requests.Response:
    headers = {
        name: request.headers[name]
        for name in REQUEST_HEADERS
        if name in request.headers
    }
    try:
        return requests.request(
            request.method,
            url,
            headers=headers,
            stream=True,
            timeout=(5, 120),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail="Internal application is unavailable"
        ) from exc


async def proxy_extractor_request(request: Request, path: str) -> StreamingResponse:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")
        if declared_length > EXTRACTOR_MAX_CONTENT_LENGTH:
            raise HTTPException(status_code=413, detail="Request body is too large")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > EXTRACTOR_MAX_CONTENT_LENGTH:
            raise HTTPException(status_code=413, detail="Request body is too large")
        body.extend(chunk)

    suffix = f"/{path}" if path else "/"
    headers = {
        "X-Forwarded-Prefix": "/extractor",
        "X-Forwarded-Host": request.headers.get("host", "localhost"),
        "X-Forwarded-Proto": request.url.scheme,
    }
    if request.client:
        headers["X-Forwarded-For"] = request.client.host
    try:
        upstream = await run_in_threadpool(
            requests.request,
            request.method,
            f"{EXTRACTOR_URL}{suffix}",
            params=list(request.query_params.multi_items()),
            data=bytes(body),
            headers={
                **{
                    name: request.headers[name]
                    for name in REQUEST_HEADERS
                    if name in request.headers
                },
                **headers,
            },
            stream=True,
            timeout=(5, 120),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail="Stream Extractor is unavailable"
        ) from exc
    return _response(upstream)


def proxy_liveproxy_request(request: Request, command: str) -> StreamingResponse:
    encoded = command.rstrip("/")
    if not BASE64_PATH.fullmatch(encoded):
        raise HTTPException(status_code=400, detail="Invalid LiveProxy command")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid LiveProxy command") from exc
    if (
        base64.b64encode(decoded.encode("ascii")).decode("ascii") != encoded
        or not LIVEPROXY_COMMAND.fullmatch(decoded)
    ):
        raise HTTPException(status_code=400, detail="Unsupported LiveProxy command")

    url = f"{LIVEPROXY_URL}/base64/{quote(encoded, safe='+/=')}/"
    upstream = _make_request(url, request)
    return _response(upstream)
