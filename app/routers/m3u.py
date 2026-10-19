"""M3U download and import endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from .. import m3u
from ..extraction import render_playlist
from ..schemas import PlaylistDetail
from ..security import require_read, require_write
from .api import detail

MAX_IMPORT_BYTES = 1_000_000

router = APIRouter(prefix="/m3u", tags=["m3u"])


@router.get(
    "/{name}.m3u",
    response_class=PlainTextResponse,
    summary="Download a refreshed M3U playlist",
    dependencies=[Depends(require_read)],
)
async def download_m3u(
    name: str,
    download: bool = False,
    api_key: str | None = Query(
        default=None,
        alias="apiKey",
        description="Optional API key for clients that cannot send X-API-Key headers.",
    ),
) -> PlainTextResponse:
    entries = m3u.load_playlist(name)
    content = await run_in_threadpool(render_playlist, entries)
    disposition = "attachment" if download else "inline"
    return PlainTextResponse(
        content,
        media_type="audio/x-mpegurl",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Content-Disposition": f'{disposition}; filename="{name}.m3u"',
        },
    )


@router.put(
    "/{name}.m3u",
    response_model=PlaylistDetail,
    summary="Import or replace a playlist from M3U text",
    dependencies=[Depends(require_write)],
)
async def import_m3u(name: str, request: Request) -> PlaylistDetail:
    body = await request.body()
    if len(body) > MAX_IMPORT_BYTES:
        raise m3u.PayloadTooLarge("El archivo M3U supera 1 MB")
    text = body.decode("utf-8-sig", errors="replace")
    entries = await run_in_threadpool(m3u.import_playlist, name, text)
    return detail(name, entries)
