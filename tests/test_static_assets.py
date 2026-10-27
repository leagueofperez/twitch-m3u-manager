import json
import re


def test_shared_template_metadata_and_static_assets(client):
    client.headers.pop("X-API-Key")
    page = client.get("/login")

    assert page.status_code == 200
    assert 'rel="icon" type="image/x-icon" href="http://testserver/static/favicon.ico"' in page.text
    assert 'rel="icon" type="image/svg+xml" href="http://testserver/static/favicon.svg"' in page.text
    assert 'rel="manifest" href="http://testserver/static/site.webmanifest"' in page.text
    assert 'rel="stylesheet" href="http://testserver/static/styles.css"' in page.text
    assert 'rel="stylesheet" href="http://testserver/static/theme.css"' in page.text
    assert 'src="http://testserver/static/theme.js"' in page.text
    assert 'data-theme-toggle' in page.text
    assert 'data-theme-icon="auto"' in page.text
    assert 'data-theme-icon="light"' in page.text
    assert 'data-theme-icon="dark"' in page.text
    assert 'data-theme-label' not in page.text
    theme_styles = client.get("/static/styles.css").text
    assert 'html[data-theme="light"] a:not(.btn):hover' in theme_styles
    assert 'html[data-theme="light"] a:hover' not in theme_styles
    shared_theme_styles = client.get("/static/theme.css").text
    assert 'html[data-theme-mode="auto"] .theme-toggle-icon' in shared_theme_styles
    assert 'html[data-theme-mode="light"] .theme-toggle-icon' in shared_theme_styles
    assert 'html[data-theme-mode="dark"] .theme-toggle-icon' in shared_theme_styles
    assert (
        '<meta property="og:image" content="http://testserver/static/og-image.png">'
        in page.text
    )
    assert '<link rel="canonical" href="http://testserver/login">' in page.text
    assert '<meta property="og:url" content="http://testserver/login">' in page.text
    assert 'name="robots" content="noindex' not in page.text
    assert (
        '<meta property="og:image:alt" content="Twitch M3U Manager: gestión de listas '
        'M3U y actualización de enlaces HLS de Twitch.">'
    ) in page.text
    assert 'name="twitter:card" content="summary_large_image"' in page.text
    assert '<meta property="og:site_name" content="Twitch M3U Manager">' in page.text
    assert '<meta property="og:title" content="Iniciar sesión · Twitch M3U Manager">' in page.text
    assert '<meta name="twitter:title" content="Iniciar sesión · Twitch M3U Manager">' in page.text
    assert (
        '<meta name="description" content="Inicia sesión en Twitch M3U Manager para '
        'administrar listas M3U de canales de Twitch y actualizar sus enlaces HLS al '
        'exportarlas.">'
    ) in page.text
    assert (
        '<meta property="og:description" content="Inicia sesión en Twitch M3U Manager '
        'para administrar listas M3U de canales de Twitch y actualizar sus enlaces HLS '
        'al exportarlas.">'
    ) in page.text
    assert (
        '<meta name="twitter:description" content="Inicia sesión en Twitch M3U Manager '
        'para administrar listas M3U de canales de Twitch y actualizar sus enlaces HLS '
        'al exportarlas.">'
    ) in page.text
    assert "twitter:site" not in page.text
    assert "Twitch Stream Extractor" not in page.text
    json_ld_match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        page.text,
        re.DOTALL,
    )
    assert json_ld_match
    structured_data = json.loads(json_ld_match.group(1))
    assert structured_data["name"] == "Iniciar sesión · Twitch M3U Manager"
    assert structured_data["url"] == "http://testserver/login"
    assert structured_data["inLanguage"] == "es"
    assert structured_data["isPartOf"]["url"] == "http://testserver/"

    for asset in (
        "favicon.ico",
        "favicon.svg",
        "favicon-16x16.png",
        "favicon-32x32.png",
        "favicon-48x48.png",
        "apple-touch-icon.png",
        "android-chrome-192x192.png",
        "android-chrome-512x512.png",
        "og-image.png",
        "site.webmanifest",
        "styles.css",
        "theme.css",
        "theme.js",
    ):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=86400"

    manifest = client.get("/static/site.webmanifest").json()
    assert manifest["name"] == "Twitch M3U Manager"
    assert manifest["short_name"] == "M3U Manager"
    assert "Administra listas M3U de canales de Twitch" in manifest["description"]

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "/extractor/extract" in robots.text


def test_canonical_and_social_urls_use_configured_public_origin(client, monkeypatch):
    client.headers.pop("X-API-Key")
    monkeypatch.setenv("TWITCH_M3U_PUBLIC_ORIGIN", "https://m3u.example.com/")
    monkeypatch.setenv("TWITCH_M3U_TWITTER_HANDLE", "@twitchm3u")

    page = client.get(
        "/login?next=%2Fmanager%2Fp%2Fdemo", headers={"Host": "internal:8000"}
    )

    assert page.status_code == 200
    assert '<link rel="canonical" href="https://m3u.example.com/login">' in page.text
    assert '<meta property="og:url" content="https://m3u.example.com/login">' in page.text
    assert "?next=" not in page.text.split('<link rel="canonical"', 1)[1].split(">", 1)[0]
    assert (
        '<meta property="og:image" content="https://m3u.example.com/static/og-image.png">'
        in page.text
    )
    assert (
        '<meta name="twitter:image" content="https://m3u.example.com/static/og-image.png">'
        in page.text
    )
    assert '<meta name="twitter:site" content="@twitchm3u">' in page.text


def test_public_origin_must_be_an_origin_without_path(monkeypatch):
    import pytest

    from app.config import get_settings

    monkeypatch.setenv("TWITCH_M3U_PUBLIC_ORIGIN", "https://example.com/path")

    with pytest.raises(ValueError, match="absolute HTTP\\(S\\) origin"):
        get_settings()
