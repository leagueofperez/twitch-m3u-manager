from pathlib import Path

from fastapi.templating import Jinja2Templates

from .config import get_settings

BASE_DIR = Path(__file__).resolve().parent


def _seo_context(request):
    settings = get_settings()
    origin = settings.public_origin or str(request.base_url).rstrip("/")
    return {
        "canonical_origin": origin,
        "canonical_url": f"{origin}{request.url.path}",
        "twitter_handle": settings.twitter_handle,
    }


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates"),
    context_processors=[_seo_context],
)
