# app.py
from pathlib import Path

from flask import Flask, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

import shortener
from config import Config
from routes.api import api
from routes.pages import pages

SHARED_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(config or {})

    @app.context_processor
    def inject_site_url():
        configured = (app.config["PUBLIC_URL"] or "").strip()
        site_url = configured or request.url_root
        if configured and request.script_root:
            site_url = f"{configured.rstrip('/')}{request.script_root}"
        return {
            "site_url": site_url.rstrip("/"),
            "shortener_enabled": shortener.is_enabled(),
        }

    app.register_blueprint(pages)
    app.register_blueprint(api)

    @app.get("/static/theme.css")
    def shared_theme_css():
        return send_from_directory(SHARED_STATIC_DIR, "theme.css")

    @app.get("/static/theme.js")
    def shared_theme_js():
        return send_from_directory(SHARED_STATIC_DIR, "theme.js")

    @app.get("/static/site.js")
    def shared_site_js():
        return send_from_directory(SHARED_STATIC_DIR, "site.js")

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)