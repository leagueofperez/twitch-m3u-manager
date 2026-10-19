"""Rutas HTML (interfaz web con Tailwind)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import m3u
from ..security import require_read
from ..templating import templates

router = APIRouter(include_in_schema=False)


def _require_page_key(request: Request) -> str | RedirectResponse:
    try:
        key = require_read(request)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        return RedirectResponse(
            f"/login?next={request.url.path}", status_code=303
        )
    return key.role


@router.get("/")
def home(request: Request):
    role = _require_page_key(request)
    if isinstance(role, RedirectResponse):
        return role
    return templates.TemplateResponse(
        request,
        "home.html",
        {"playlists": m3u.list_playlists(), "api_key_role": role},
    )


@router.get("/p/{name}")
def playlist(request: Request, name: str):
    role = _require_page_key(request)
    if isinstance(role, RedirectResponse):
        return role
    entries = m3u.load_playlist(name)
    return templates.TemplateResponse(
        request,
        "playlist.html",
        {
            "name": name,
            "entries": entries,
            "api_key_role": role,
        },
    )
