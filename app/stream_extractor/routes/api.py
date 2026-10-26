import shortener
from flask import Blueprint, current_app, jsonify, request

from services.extraction import extract_streams
from shortener import ShortenerError
from twitch.errors import TwitchError
from web.errors import sanitize_error

api = Blueprint("api", __name__)


@api.route("/extract", methods=["POST"])
def extract():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Se esperaba un objeto JSON."}), 400

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "URL vacía"}), 400

    try:
        return jsonify({"streams": extract_streams(url.strip())})
    except TwitchError as exc:
        return jsonify({"error": sanitize_error(str(exc))}), 400
    except Exception as exc:
        current_app.logger.exception("Error no controlado en /extract")
        return jsonify(
            {"error": sanitize_error(f"{exc.__class__.__name__}: {exc}")}
        ), 500


@api.route("/shorten", methods=["POST"])
def shorten():
    if not shortener.is_enabled():
        return (
            jsonify({"error": "El acortado no está configurado en este servidor."}),
            503,
        )

    if shortener.rate_limited(request.remote_addr or "desconocida"):
        return jsonify({"error": "Demasiadas peticiones. Espera un minuto."}), 429

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Se esperaba un objeto JSON."}), 400

    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"error": "URL vacía"}), 400

    values = ("slug", "title", "ts", "sig")
    if any(key not in data for key in values):
        return jsonify({"error": "Faltan datos de firma."}), 400
    if not isinstance(data["slug"], str) or not isinstance(data["title"], str):
        return jsonify({"error": "Los datos del enlace no son válidos."}), 400
    if not isinstance(data["sig"], str):
        return jsonify({"error": "Los datos del enlace no son válidos."}), 400

    try:
        return jsonify(
            shortener.shorten(
                url.strip(),
                data["slug"],
                data["title"],
                data["ts"],
                data["sig"],
            )
        )
    except ShortenerError as exc:
        return jsonify({"error": sanitize_error(str(exc))}), exc.status
    except Exception as exc:
        current_app.logger.exception("Error no controlado en /shorten")
        return jsonify(
            {"error": sanitize_error(f"{exc.__class__.__name__}: {exc}")}
        ), 500
