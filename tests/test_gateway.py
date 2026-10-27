import asyncio
import base64
from unittest.mock import patch

import pytest
import requests
from fastapi import HTTPException
from starlette.requests import Request

from app.auth_store import create_api_key
from app.config import get_settings
from app.routers.gateway import proxy_extractor_request


def _upstream_response(body=b"ok", status=200, content_type="text/plain"):
    response = requests.Response()
    response.status_code = status
    response.headers["Content-Type"] = content_type
    response._content = body
    response._content_consumed = True
    return response


def test_landing_links_to_the_three_apps_and_new_apps_require_auth(client):
    landing = client.get("/")
    assert landing.status_code == 200
    assert 'href="/manager"' in landing.text
    assert 'href="/extractor"' in landing.text
    assert 'href="/liveproxy"' in landing.text
    assert 'data-theme-toggle' in landing.text

    client.headers.pop("X-API-Key")
    extractor = client.get("/extractor", follow_redirects=False)
    assert extractor.status_code == 303
    assert extractor.headers["location"] == "/login?next=/extractor"
    liveproxy_page = client.get("/liveproxy", follow_redirects=False)
    assert liveproxy_page.status_code == 303
    assert liveproxy_page.headers["location"] == "/login?next=/liveproxy"
    proxy = client.get("/liveproxy/base64/not-valid/", follow_redirects=False)
    assert proxy.status_code == 401


def test_extractor_gateway_forwards_prefixed_requests_with_auth(client):
    with patch(
        "app.routers.gateway.requests.request",
        return_value=_upstream_response(b'{"streams":[]}', content_type="application/json"),
    ) as send:
        response = client.post(
            "/extractor/extract?source=ui",
            json={"url": "twitch.tv/channel"},
        )

    assert response.status_code == 200
    assert response.json() == {"streams": []}
    assert send.call_args.args[:2] == (
        "POST",
        "http://127.0.0.1:5000/extract",
    )
    assert send.call_args.kwargs["params"] == [("source", "ui")]
    assert send.call_args.kwargs["headers"]["X-Forwarded-Prefix"] == "/extractor"


def test_extractor_gateway_rejects_oversized_bodies_before_upstream(client):
    with patch("app.routers.gateway.requests.request") as send:
        response = client.post(
            "/extractor/extract",
            content=b"x" * (16_384 + 1),
            headers={"content-type": "application/octet-stream"},
        )

    assert response.status_code == 413
    send.assert_not_called()


def test_extractor_gateway_limits_chunked_bodies(client):
    chunks = iter([b"x" * 9_000, b"x" * 9_000, b"x", b""])

    async def receive():
        body = next(chunks)
        return {
            "type": "http.request",
            "body": body,
            "more_body": bool(body),
        }

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/extractor/extract",
            "raw_path": b"/extractor/extract",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        },
        receive,
    )
    with patch("app.routers.gateway.requests.request") as send:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(proxy_extractor_request(request, "extract"))
    assert exc_info.value.status_code == 413
    send.assert_not_called()


def test_extractor_read_api_accepts_public_key_but_shorten_requires_private(client):
    _key, public_key = create_api_key(
        get_settings().auth_db_path, "extractor-reader", "public", "test-admin"
    )
    with patch(
        "app.routers.gateway.requests.request",
        return_value=_upstream_response(b'{"streams":[]}', content_type="application/json"),
    ):
        response = client.post(
            "/extractor/extract",
            json={"url": "twitch.tv/channel"},
            headers={"X-API-Key": public_key},
        )
    assert response.status_code == 200

    denied = client.post(
        "/extractor/shorten",
        json={},
        headers={"X-API-Key": public_key},
    )
    assert denied.status_code == 403


def test_liveproxy_only_accepts_allowlisted_twitch_commands(client):
    command = base64.b64encode(
        b"streamlink https://twitch.tv/channel_1 best"
    ).decode()
    with patch(
        "app.routers.gateway.requests.request",
        return_value=_upstream_response(b"stream", content_type="video/mp2t"),
    ) as send:
        response = client.get(f"/liveproxy/base64/{command}/?ignored=value")

    assert response.status_code == 200
    assert response.content == b"stream"
    assert send.call_args.args[:2] == (
        "GET",
        f"http://127.0.0.1:53422/base64/{command}/",
    )
    assert "params" not in send.call_args.kwargs

    invalid = base64.b64encode(b"python -c 'import os'").decode()
    with patch("app.routers.gateway.requests.request") as send:
        response = client.get(f"/liveproxy/base64/{invalid}/")
    assert response.status_code == 400
    send.assert_not_called()


def test_liveproxy_requires_private_key_and_offers_a_browser_ui(client):
    _key, public_key = create_api_key(
        get_settings().auth_db_path, "proxy-reader", "public", "test-admin"
    )
    assert client.get("/liveproxy", headers={"X-API-Key": public_key}).status_code == 403

    page = client.get("/liveproxy?channel=Example")
    assert page.status_code == 200
    assert "example" in page.text
    assert "/liveproxy/base64/" in page.text


def test_cookie_authenticated_extractor_posts_require_same_origin(client):
    client.headers.pop("X-API-Key")
    login = client.post(
        "/auth/login",
        json={
            "username": "test-admin",
            "password": "test-password-long-enough",
        },
        headers={"Origin": "http://testserver"},
    )
    assert login.status_code == 200

    denied = client.post("/extractor/extract", json={"url": "channel"})
    assert denied.status_code == 403

    with patch(
        "app.routers.gateway.requests.request",
        return_value=_upstream_response(b'{"streams":[]}', content_type="application/json"),
    ):
        allowed = client.post(
            "/extractor/extract",
            json={"url": "channel"},
            headers={"Origin": "http://testserver"},
        )
    assert allowed.status_code == 200
