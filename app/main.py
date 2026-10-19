from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .m3u import M3UError
from .routers import api, m3u as m3u_router, web
from .templating import BASE_DIR, templates


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().data_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Twitch M3U Manager",
    description="Manage M3U playlists with refreshed Twitch HLS stream URLs.",
    version=__version__,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(web.router)
app.include_router(api.router)
app.include_router(m3u_router.router)


@app.get("/health", tags=["api"], summary="Service health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.exception_handler(M3UError)
async def m3u_error_handler(request: Request, exc: M3UError):
    if request.url.path.startswith(("/api", "/m3u")):
        headers = {}
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            headers["Retry-After"] = retry_after
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code, headers=headers)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status": exc.status_code, "message": str(exc)},
        status_code=exc.status_code,
    )
