"""Rutas HTML (interfaz web con Tailwind)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from .. import m3u
from ..security import require_auth
from ..templating import templates

router = APIRouter(dependencies=[Depends(require_auth)], include_in_schema=False)


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {"playlists": m3u.list_playlists()},
    )


@router.get("/p/{name}")
def playlist(request: Request, name: str):
    entries = m3u.load_playlist(name)
    return templates.TemplateResponse(
        request,
        "playlist.html",
        {
            "name": name,
            "entries": entries,
        },
    )
