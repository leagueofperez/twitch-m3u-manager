from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth_store import bootstrap_user, initialize
from .config import get_settings
from .m3u import M3UError
from .routers import api, auth, m3u as m3u_router, web
from .security import require_read
from .templating import BASE_DIR, templates


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
    bootstrap_user(
        settings.auth_db_path, settings.login_username, settings.login_password
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
    for path, path_item in schema["paths"].items():
        if path in {"/health", "/login", "/auth/login", "/auth/logout"}:
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and "responses" in operation:
                operation["security"] = [{"ApiKeyHeader": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _authenticated_openapi


@app.middleware("http")
async def disable_private_route_caching(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        path == "/"
        or path.startswith(("/p/", "/api/", "/m3u/", "/docs", "/openapi.json"))
    ):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/docs", include_in_schema=False, dependencies=[Depends(require_read)])
def docs():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Twitch M3U Manager API")


@app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_read)])
def openapi():
    return app.openapi()


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
