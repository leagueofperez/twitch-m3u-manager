from __future__ import annotations

from contextlib import asynccontextmanager
import base64
import re
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from . import __version__
from .auth_store import PRIVATE, bootstrap_user, initialize
from .config import get_settings
from .m3u import M3UError
from .routers import api, auth, m3u as m3u_router, web
from .routers.gateway import proxy_extractor_request, proxy_liveproxy_request
from .security import require_read, require_same_origin
from .templating import BASE_DIR, templates

LIVEPROXY_CHANNEL = re.compile(r"[A-Za-z0-9_]{1,25}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    initialize(settings.auth_db_path)
    if not settings.login_username or not settings.login_password:
        raise RuntimeError(
            "Configure TWITCH_M3U_LOGIN_USERNAME and TWITCH_M3U_LOGIN_PASSWORD "
            "before starting the app."
        )
    initial_api_key = bootstrap_user(
        settings.auth_db_path, settings.login_username, settings.login_password
    )
    if initial_api_key:
        print(
            "Initial private API key for configured user "
            f"{settings.login_username} (shown once): {initial_api_key}",
            flush=True,
        )
        print(
            "Private API keys can read and write playlists. DO NOT SHARE.",
            flush=True,
        )
    yield


app = FastAPI(
    title="Twitch M3U Manager",
    description="Manage M3U playlists with refreshed Twitch HLS stream URLs.",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(web.router)
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(m3u_router.router)


@app.get("/", include_in_schema=False)
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.api_route(
    "/extractor/",
    methods=["GET", "POST", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
@app.api_route(
    "/extractor",
    methods=["GET", "POST", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
@app.api_route(
    "/extractor/{path:path}",
    methods=["GET", "POST", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def extractor_gateway(request: Request, path: str = ""):
    return await proxy_extractor_request(request, path)


@app.get(
    "/liveproxy/base64/{command:path}",
    response_class=StreamingResponse,
    include_in_schema=False,
)
def liveproxy_gateway(request: Request, command: str):
    return proxy_liveproxy_request(request, command)


@app.get("/liveproxy", include_in_schema=False)
def liveproxy_home(request: Request, channel: str = ""):
    channel = channel.strip().lower()
    stream_path = None
    if channel:
        if LIVEPROXY_CHANNEL.fullmatch(channel):
            command = f"streamlink https://twitch.tv/{channel} best".encode("ascii")
            encoded = base64.b64encode(command).decode("ascii")
            stream_path = f"/liveproxy/base64/{encoded}/"
        else:
            channel = ""
    return templates.TemplateResponse(
        request,
        "liveproxy.html",
        {
            "channel": channel,
            "stream_path": stream_path,
            "api_key_kind": getattr(request.state, "api_key_kind", None),
        },
    )


def _authenticated_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schemes["ApiKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
    }
    for path, path_item in schema["paths"].items():
        if path in {"/health", "/login", "/auth/login", "/auth/logout"}:
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and "responses" in operation:
                operation["security"] = [
                    {"ApiKeyHeader": [], "BearerAuth": []}
                ]
    app.openapi_schema = schema
    return schema


app.openapi = _authenticated_openapi


@app.middleware("http")
async def authenticate_apps_and_set_cache_headers(request: Request, call_next):
    path = request.url.path
    in_extractor = path == "/extractor" or path.startswith("/extractor/")
    in_liveproxy = path == "/liveproxy" or path.startswith("/liveproxy/")
    extractor_asset = in_extractor and path.startswith("/extractor/static/")
    if (in_extractor and not extractor_asset) or in_liveproxy:
        try:
            key = require_read(request)
            if (
                in_liveproxy or path == "/extractor/shorten"
            ) and key.kind != PRIVATE:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="A private API key or browser login is required",
                )
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and not request.state.api_key_auth
            ):
                require_same_origin(request)
        except HTTPException as exc:
            if (
                exc.status_code == status.HTTP_401_UNAUTHORIZED
                and request.method in {"GET", "HEAD"}
                and path in {"/extractor", "/extractor/", "/liveproxy"}
            ):
                return RedirectResponse(
                    f"/login?next={quote(request.url.path, safe='/')}",
                    status_code=303,
                )
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers,
            )

    response = await call_next(request)
    if path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    if path.startswith("/extractor/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    if (
        path == "/"
        or path.startswith(
            (
                "/manager",
                "/p/",
                "/api/",
                "/m3u/",
                "/docs",
                "/openapi.json",
                "/extractor",
                "/liveproxy",
            )
        )
    ):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/docs", include_in_schema=False)
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Twitch M3U Manager API")


@app.get("/openapi.json", include_in_schema=False)
def openapi():
    return app.openapi()


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return FileResponse(BASE_DIR / "static" / "robots.txt", media_type="text/plain")


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
