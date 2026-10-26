#!/usr/bin/env bash
#
# tools/generate-assets.sh
#
# Rasteriza todos los iconos e imagenes sociales desde los SVG maestros de
# assets/. Es la unica fuente de verdad visual: para cambiar la marca se
# edita assets/icon.svg y se ejecuta esto (`make icons`); no hay que volver
# a crear ningun PNG a mano.
#
# Requisitos (host, no la imagen Docker):
#   librsvg2-bin   -> rsvg-convert, rasterizador SVG
#   imagemagick    -> convert, solo para empaquetar el .ico
#   fontconfig + al menos una fuente  -> para el <text> de la imagen social
#
# python:3.11-slim NO trae nada de esto; por eso el generador se ejecuta
# en el host y los PNG resultantes se commitean en static/.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSETS="$ROOT/assets"
OUT="$ROOT/static"

THEME_COLOR="#6441a5"
BG_COLOR="#ffffff"

ICON_SVG="$ASSETS/icon.svg"
OG_TEMPLATE="$ASSETS/og.svg"

die() { echo "error: $*" >&2; exit 1; }

command -v rsvg-convert >/dev/null 2>&1 || die "falta rsvg-convert (apt install librsvg2-bin)"
command -v convert       >/dev/null 2>&1 || die "falta convert (apt install imagemagick)"
[ -f "$ICON_SVG" ]  || die "no existe $ICON_SVG"
[ -f "$OG_TEMPLATE" ] || die "no existe $OG_TEMPLATE"

mkdir -p "$OUT"

# --- matriz de tamaños -------------------------------------------------------
# origen:tamaño:salida. Añadir un icono nuevo es añadir una línea aquí.
render() {
    local src="$1" size="$2" dest="$3"
    rsvg-convert --width "$size" --height "$size" --background-color none \
        "$src" --output "$dest"
    echo "  $(basename "$dest")  ${size}x${size}"
}

echo "Generando iconos desde assets/icon.svg"
render "$ICON_SVG" 16  "$OUT/favicon-16x16.png"
render "$ICON_SVG" 32  "$OUT/favicon-32x32.png"
render "$ICON_SVG" 48  "$OUT/favicon-48x48.png"
render "$ICON_SVG" 180 "$OUT/apple-touch-icon.png"
render "$ICON_SVG" 192 "$OUT/android-chrome-192x192.png"
render "$ICON_SVG" 512 "$OUT/android-chrome-512x512.png"

# El favicon vectorial se copia tal cual: es el que usan los navegadores
# modernos y se ve nítido a cualquier densidad de pantalla.
cp "$ICON_SVG" "$OUT/favicon.svg"

echo "Empaquetando favicon.ico"
convert "$OUT/favicon-16x16.png" \
        "$OUT/favicon-32x32.png" \
        "$OUT/favicon-48x48.png" \
        "$OUT/favicon.ico"

# --- imagen social ----------------------------------------------------------
# rsvg-convert no resuelve <image href="...svg">, asi que el contenido de
# icon.svg se inyecta en la plantilla og.svg sustituyendo {{ICON_BODY}}.
# Se hace en Python porque separar XML con sed/awk sobre contenido multilinea
# es fragil, y el proyecto ya es Python.
echo "Construyendo la imagen social"
command -v python3 >/dev/null 2>&1 || die "falta python3 para inyectar la marca"

OG_BUILT="$(mktemp)"
trap 'rm -f "$OG_BUILT"' EXIT

python3 - "$ICON_SVG" "$OG_TEMPLATE" "$OG_BUILT" <<'PY'
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
icon_path, template_path, out_path = sys.argv[1:4]

ET.register_namespace("", SVG_NS)
root = ET.parse(icon_path).getroot()

body = "".join(ET.tostring(child, encoding="unicode") for child in root)
# Cada hijo lleva xmlns propio porque se serializa aislado; el <g> que lo
# contiene ya declara el namespace, asi que sobra.
body = body.replace(f' xmlns="{SVG_NS}"', "")

template = open(template_path, encoding="utf-8").read()
if "{{ICON_BODY}}" not in template:
    sys.exit("error: la plantilla og.svg no contiene el marcador {{ICON_BODY}}")

open(out_path, "w", encoding="utf-8").write(template.replace("{{ICON_BODY}}", body))
PY

rsvg-convert --width 1200 --height 630 "$OG_BUILT" --output "$OUT/og-image.png"
echo "  og-image.png  1200x630"

# --- manifest ---------------------------------------------------------------
# Se genera desde el script para que los tamaños tengan una sola definicion.
echo "Escribiendo site.webmanifest"
cat > "$OUT/site.webmanifest" <<JSON
{
  "name": "Twitch Stream Extractor",
  "short_name": "Extractor",
  "description": "Extrae URLs m3u8 de streams de Twitch en vivo y VODs por calidad.",
  "lang": "es",
  "dir": "ltr",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "$BG_COLOR",
  "theme_color": "$THEME_COLOR",
  "icons": [
    { "src": "/static/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any" },
    { "src": "/static/android-chrome-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/static/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/static/android-chrome-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
JSON

cat > "$OUT/robots.txt" <<'TXT'
User-agent: *
Allow: /

# /extract es un endpoint POST: no hay nada que indexar.
Disallow: /extract
TXT

echo "Listo. Iconos en static/"