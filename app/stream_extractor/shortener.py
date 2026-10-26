# shortener.py
"""Acortado de URLs de stream con short.io.

El destino de una URL m3u8 de Twitch es un token que caduca en pocos minutos,
así que la URL larga no es manejable en un reproductor. Aquí se publica esa
misma URL bajo un slug estable del dominio propio.

La clave de short.io nunca sale del servidor: todo esto corre en Flask y el
navegador solo recibe la URL corta ya creada.

Configuración por entorno:
    SHORT_IO_API_KEY   Clave secreta (Integrations & API en el panel de short.io)
    SHORT_IO_DOMAIN    Dominio propio, p. ej. enlaces.midominio.com

Por qué `requests` y no el cliente de PyPI
------------------------------------------
Existe `short-io-api-client`, pero no es de short.io: es un paquete de un tercero
auto-generado con openapi-python-client a partir del OpenAPI spec, sin autor, sin
licencia declarada y con una unica version publicada (1.0.0, 2026-01-26). No
aparece enlazado en la documentacion de short.io.

short.io no publica un cliente oficial para Python: sus SDK oficiales son
@short.io/client-browser y @short.io/client-node, ambos de JavaScript, y su
propia guia de Python usa `requests` en crudo, que es lo que hace este modulo.

Aun asi se evaluo migrar. El flujo pasaria de 56 a 22 lineas, pero arrastraria
httpx (una segunda pila HTTP, el proyecto ya usa requests), attrs y
python-dateutil; ocuparia 1.75 MB y 195 modelos generados para tres llamadas; y su
transporte httpx es mas dificil de sustituir en tests que el seam `_request` de
este modulo. Se opto por no anadir esa dependencia.
"""

import hashlib
import hmac
import logging
import os
import re
import threading
import time
from collections import OrderedDict

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.short.io"
TIMEOUT = 15

# Cuánto tiempo una URL emitida por /extract sigue siendo acortable.
ISSUED_TTL_SECONDS = 30 * 60

# Límite de peticiones por IP y ventana, para no agotar la cuota de short.io.
# Ojo: el contador vive en la memoria del proceso, y gunicorn corre con varios
# workers, así que el tope real es WORKERS * RATE_LIMIT_MAX por minuto. Con los
# valores por defecto (4 workers) son hasta 80/min. Es una guarda best-effort
# contra el abuso casual, no un límite estricto; la garantía dura es la firma.
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 60

SLUG_UNSAFE = re.compile(r"[^a-z0-9_-]+")
SLUG_MAX_LEN = 64
TITLE_MAX_LEN = 80


class ShortenerError(RuntimeError):
    """Error apto para devolver al cliente. Nunca incluye la clave de short.io."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def api_key():
    return (os.environ.get("SHORT_IO_API_KEY") or "").strip()


def domain():
    return (os.environ.get("SHORT_IO_DOMAIN") or "").strip()


def is_enabled():
    return bool(api_key() and domain())


# --- URLs emitidas: firma, no caché -----------------------------------------
# /shorten solo debe aceptar URLs que este servidor acaba de emitir; si no, la
# app se convierte en un acortador de phishing abierto en el dominio propio.
#
# La primera versión lo resolvía guardando las URLs en un diccionario en
# memoria, pero gunicorn corre con 4 workers y cada uno tiene su propia copia:
# extraer por un worker y acortar por otro fallaba. Tampoco servía un archivo
# compartido ni bajar a un solo worker.
#
# La solución es no guardar nada. /extract firma cada URL con HMAC y /shorten
# comprueba la firma. Es sin estado, asi que da igual en que worker caiga cada
# peticion, y sobrevive a reinicios del contenedor.
def signature(ts, url, slug, title):
    """HMAC-SHA256 sobre los datos del enlace, con la clave de short.io."""
    message = "\n".join([str(ts), url, slug, title]).encode()
    return hmac.new(api_key().encode(), message, hashlib.sha256).hexdigest()


def issue(url, slug, title):
    """Devuelve el bloque que el navegador reenviará a /shorten."""
    ts = int(time.time())
    return {
        "slug": slug,
        "title": title,
        "ts": ts,
        "sig": signature(ts, url, slug, title),
    }


def verify(ts, url, slug, title, sig):
    """True si los datos son autenticos y no han caducado."""
    try:
        age = time.time() - int(ts)
    except (TypeError, ValueError):
        return False
    if age < 0 or age > ISSUED_TTL_SECONDS:
        return False
    expected = signature(ts, url, slug, title)
    return hmac.compare_digest(expected, sig or "")


# --- límite de peticiones ----------------------------------------------------
_hits = OrderedDict()
_hits_lock = threading.Lock()


def rate_limited(identity):
    now = time.monotonic()
    with _hits_lock:
        stamps = _hits.get(identity) or []
        stamps = [t for t in stamps if now - t < RATE_LIMIT_WINDOW]
        if len(stamps) >= RATE_LIMIT_MAX:
            _hits[identity] = stamps
            return True
        stamps.append(now)
        _hits[identity] = stamps
        _hits.move_to_end(identity)
        while len(_hits) > 1000:
            _hits.popitem(last=False)
    return False


# --- slug --------------------------------------------------------------------
def slug_for(is_live, target, quality):
    """Construye el slug estable de una calidad concreta de un canal.

    El slug solo con el canal no valdría: una extracción devuelve varias
    calidades y todas apuntarían al mismo path, con lo que solo sobreviviría
    una. De ahí el sufijo de calidad.
    """
    base = f"{target}-" if is_live else f"vod-{target}-"
    slug = SLUG_UNSAFE.sub("", f"{base}{quality}".lower())
    return slug[:SLUG_MAX_LEN].strip("-_")


def title_for(is_live, target, quality):
    """Título legible del enlace: "Twitch caedrel 1080p60".

    En un VOD no hay nombre de canal en la URL de entrada, así que se marca
    como VOD en vez de dejar el ID solto, que se leería como si fuera el
    nombre del canal.
    """
    who = target if is_live else f"VOD {target}"
    return f"Twitch {who} {quality}"[:TITLE_MAX_LEN]


# --- cliente de short.io -----------------------------------------------------
def _headers():
    return {
        "Authorization": api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request(method, path, **kwargs):
    try:
        return requests.request(
            method, f"{API_BASE}{path}", headers=_headers(), timeout=TIMEOUT, **kwargs
        )
    except requests.RequestException as exc:
        raise ShortenerError(
            f"No se pudo contactar con short.io: {exc.__class__.__name__}.",
            status=502,
        ) from exc


def _short_url(payload):
    return payload.get("secureShortURL") or payload.get("shortURL")


def shorten(url, slug, title, ts, sig):
    """Crea o actualiza la URL corta de `url` y devuelve la respuesta.

    Antes de tocar short.io se comprueba la firma emitida junto a la URL: sin
    ella, cualquiera podria usar esta app para acortar enlaces arbitrarios
    bajo el dominio propio.

    Flujo (según la API de short.io):
      GET /links/expand            ¿existe ya el path?
        404                        POST /links           se crea
        200, misma URL             se devuelve tal cual
        200, otra URL              POST /links/{id}      se actualiza

    No se intenta crear a ciegas: POST /links devuelve 409 si el path ya
    existe con otro destino, y hace falta el idString para poder actualizar.
    """
    if not verify(ts, url, slug, title, sig):
        raise ShortenerError("Esa URL no la generó esta app o ha caducado.")

    current = _request("GET", "/links/expand", params={"domain": domain(), "path": slug})

    if current.status_code == 404:
        created = _request(
            "POST",
            "/links",
            json={
                "originalURL": url,
                "domain": domain(),
                "path": slug,
                "title": title,
                "allowDuplicates": False,
            },
        )
        if created.status_code not in (200, 201):
            raise _api_error("crear", created)
        return {
            "shortUrl": _short_url(created.json()),
            "slug": slug,
            "title": title,
            "action": "created",
        }

    if current.status_code != 200:
        raise _api_error("consultar", current)

    info = current.json()
    if info.get("originalURL") == url:
        return {
            "shortUrl": _short_url(info),
            "slug": slug,
            "title": info.get("title") or title,
            "action": "unchanged",
        }

    link_id = info.get("idString")
    if not link_id:
        raise ShortenerError("short.io no devolvió el identificador del enlace.", status=502)

    updated = _request("POST", f"/links/{link_id}", json={"originalURL": url, "title": title})
    if updated.status_code not in (200, 201):
        raise _api_error("actualizar", updated)

    return {
        "shortUrl": _short_url(updated.json()),
        "slug": slug,
        "title": title,
        "action": "updated",
    }


def _api_error(action, response):
    """Traduce un error de short.io sin filtrar la clave ni el cuerpo entero."""
    try:
        message = response.json().get("message") or response.json().get("error")
    except ValueError:
        message = None

    if response.status_code == 401:
        return ShortenerError("La clave de short.io no es válida.", status=502)
    if response.status_code == 429:
        return ShortenerError("short.io está limitando peticiones, inténtalo en un momento.", status=429)

    detail = f": {message}" if message else ""
    log.warning("short.io %s -> HTTP %s%s", action, response.status_code, detail)
    return ShortenerError(f"short.io no pudo {action} el enlace (HTTP {response.status_code}).", status=502)