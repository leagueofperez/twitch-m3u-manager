from flask import Blueprint, current_app, render_template, request

from services.extraction import extract_streams
from twitch.errors import TwitchError
from web.errors import sanitize_error

pages = Blueprint("pages", __name__)


@pages.route("/", methods=["GET", "POST"])
def index():
    streams = []
    error = None
    url = ""
    status_code = 200

    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        if not url:
            error = "URL vacía"
        else:
            try:
                streams = extract_streams(url)
            except TwitchError as exc:
                error = sanitize_error(str(exc))
            except Exception as exc:
                current_app.logger.exception("Error no controlado en la página principal")
                error = sanitize_error(f"{exc.__class__.__name__}: {exc}")
                status_code = 500

    return (
        render_template("index.html", streams=streams, error=error, input_url=url),
        status_code,
    )
