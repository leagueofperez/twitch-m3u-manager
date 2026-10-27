import json
import re

import pytest

HUB_TITLE = "Herramientas · Twitch Tools"
HUB_DESCRIPTION = (
    "Elige entre M3U Manager, Stream Extractor y LiveProxy: herramientas para "
    "gestionar listas M3U y reproducir streams de Twitch."
)
HUB_IMAGE_ALT = "Twitch Tools: M3U Manager, Stream Extractor y LiveProxy."

MANAGER_TITLE = "M3U Manager · Twitch Tools"
MANAGER_DESCRIPTION = (
    "Crea y administra listas M3U de canales de Twitch y actualiza sus enlaces "
    "HLS al exportarlas."
)
MANAGER_IMAGE_ALT = "M3U Manager: administra listas M3U de canales de Twitch."

LIVEPROXY_TITLE = "LiveProxy · Twitch Tools"
LIVEPROXY_DESCRIPTION = (
    "Genera una URL de reproducción protegida para un canal de Twitch con "
    "LiveProxy."
)
LIVEPROXY_IMAGE_ALT = "LiveProxy: genera URLs de reproducción para canales de Twitch."

LOGIN_TITLE = "Iniciar sesión · Twitch Tools"
LOGIN_DESCRIPTION = (
    "Inicia sesión en Twitch Tools para administrar listas M3U y usar las "
    "herramientas de Twitch."
)


def _structured_data(page):
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        page.text,
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


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
    assert 'src="http://testserver/static/site.js"' in page.text
    assert 'data-theme-toggle' in page.text
    assert 'class="site-header"' in page.text
    assert 'class="site-menu"' in page.text
    assert 'class="site-nav-toggle"' in page.text
    assert '>Herramientas</a>' in page.text
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
    assert "@media (max-width: 767px)" in shared_theme_styles
    assert ".site-menu[open] ~ .site-nav" in shared_theme_styles
    shared_site_script = client.get("/static/site.js").text
    assert "details.site-menu" in shared_site_script
    assert "'(min-width: 768px)'" in shared_site_script
    assert '<meta property="og:site_name" content="Twitch Tools">' in page.text
    assert '<meta property="og:title" content="Iniciar sesión">' in page.text
    assert '<meta name="twitter:title" content="Iniciar sesión">' in page.text
    assert (
        f'<meta property="og:image" content="http://testserver/static/'
        'og-twitch-tools.png">' in page.text
    )
    assert (
        f'<meta property="og:image:alt" content="{HUB_IMAGE_ALT}">' in page.text
    )
    assert '<link rel="canonical" href="http://testserver/login">' in page.text
    assert '<meta property="og:url" content="http://testserver/login">' in page.text
    assert 'name="robots" content="noindex' not in page.text
    assert '<meta name="twitter:card" content="summary_large_image">' in page.text
    assert f'<meta name="description" content="{LOGIN_DESCRIPTION}">' in page.text
    assert f'<meta property="og:description" content="{LOGIN_DESCRIPTION}">' in page.text
    assert f'<meta name="twitter:description" content="{LOGIN_DESCRIPTION}">' in page.text
    assert f'<meta name="twitter:image:alt" content="{HUB_IMAGE_ALT}">' in page.text
    assert "twitter:site" not in page.text
    assert "Twitch M3U Manager" not in page.text
    assert "Twitch Stream Extractor" not in page.text

    structured_data = _structured_data(page)
    assert structured_data["name"] == LOGIN_TITLE
    assert structured_data["url"] == "http://testserver/login"
    assert structured_data["image"] == "http://testserver/static/og-twitch-tools.png"
    assert structured_data["inLanguage"] == "es"
    assert structured_data["isPartOf"]["name"] == "Twitch Tools"
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
        "og-twitch-tools.png",
        "og-liveproxy.png",
        "site.webmanifest",
        "styles.css",
        "theme.css",
        "theme.js",
        "site.js",
    ):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=86400"

    manifest = client.get("/static/site.webmanifest").json()
    assert manifest["name"] == "Twitch Tools"
    assert manifest["short_name"] == "Twitch Tools"
    assert "Herramientas para gestionar listas M3U" in manifest["description"]

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "User-agent: *" in robots.text
    assert "/extractor/extract" in robots.text


def test_landing_and_tools_expose_specific_social_metadata(client):
    landing = client.get("/")
    assert landing.status_code == 200
    assert f"<title>{HUB_TITLE}</title>" in landing.text
    assert '<meta property="og:site_name" content="Twitch Tools">' in landing.text
    assert '<meta property="og:title" content="Twitch Tools">' in landing.text
    assert f'<meta property="og:description" content="{HUB_DESCRIPTION}">' in landing.text
    assert '<meta property="og:url" content="http://testserver/">' in landing.text
    assert (
        '<meta property="og:image" content="http://testserver/static/'
        'og-twitch-tools.png">' in landing.text
    )
    assert f'<meta property="og:image:alt" content="{HUB_IMAGE_ALT}">' in landing.text
    assert (
        '<meta name="twitter:image" content="http://testserver/static/'
        'og-twitch-tools.png">' in landing.text
    )
    assert _structured_data(landing)["image"] == (
        "http://testserver/static/og-twitch-tools.png"
    )

    manager = client.get("/manager")
    assert manager.status_code == 200
    assert f"<title>{MANAGER_TITLE}</title>" in manager.text
    assert '<meta property="og:title" content="M3U Manager">' in manager.text
    assert (
        f'<meta property="og:description" content="{MANAGER_DESCRIPTION}">'
        in manager.text
    )
    assert '<meta property="og:url" content="http://testserver/manager">' in manager.text
    assert (
        '<meta property="og:image" content="http://testserver/static/og-image.png">'
        in manager.text
    )
    assert (
        f'<meta property="og:image:alt" content="{MANAGER_IMAGE_ALT}">'
        in manager.text
    )
    assert (
        f'<meta name="twitter:image:alt" content="{MANAGER_IMAGE_ALT}">'
        in manager.text
    )

    liveproxy = client.get("/liveproxy")
    assert liveproxy.status_code == 200
    assert f"<title>{LIVEPROXY_TITLE}</title>" in liveproxy.text
    assert '<meta property="og:title" content="LiveProxy">' in liveproxy.text
    assert (
        f'<meta property="og:description" content="{LIVEPROXY_DESCRIPTION}">'
        in liveproxy.text
    )
    assert (
        '<meta property="og:url" content="http://testserver/liveproxy">'
        in liveproxy.text
    )
    assert (
        '<meta property="og:image" content="http://testserver/static/'
        'og-liveproxy.png">' in liveproxy.text
    )
    assert (
        f'<meta property="og:image:alt" content="{LIVEPROXY_IMAGE_ALT}">'
        in liveproxy.text
    )
    assert (
        '<meta name="twitter:image" content="http://testserver/static/'
        'og-liveproxy.png">' in liveproxy.text
    )


def test_playlist_metadata_uses_the_playlist_name_and_entry_count(client):
    client.post("/api/playlists", json={"name": "mi-lista"})
    client.post("/api/playlists/mi-lista/channels", json={"channels": "alfa,beta"})

    page = client.get("/manager/p/mi-lista")
    assert page.status_code == 200
    assert "<title>mi-lista · M3U Manager · Twitch Tools</title>" in page.text
    assert '<meta property="og:title" content="mi-lista">' in page.text
    assert (
        '<meta property="og:description" content="Lista M3U «mi-lista» con 2 '
        'entradas de canales de Twitch.">' in page.text
    )
    assert (
        '<meta property="og:image" content="http://testserver/static/og-image.png">'
        in page.text
    )


def test_login_preview_matches_the_protected_tool(client):
    client.headers.pop("X-API-Key")
    cases = (
        (
            "/manager",
            "M3U Manager",
            "Inicia sesión para administrar listas M3U de canales de Twitch.",
            "/static/og-image.png",
            MANAGER_IMAGE_ALT,
        ),
        (
            "/manager/p/demo",
            "M3U Manager",
            "Inicia sesión para administrar listas M3U de canales de Twitch.",
            "/static/og-image.png",
            MANAGER_IMAGE_ALT,
        ),
        (
            "/extractor",
            "Stream Extractor",
            "Inicia sesión para extraer URLs m3u8 de streams y VODs de Twitch.",
            "/extractor/static/og-image.png",
            "Stream Extractor: obtén URLs m3u8 de streams y VODs de Twitch.",
        ),
        (
            "/liveproxy",
            "LiveProxy",
            "Inicia sesión para generar URLs de reproducción de canales de Twitch.",
            "/static/og-liveproxy.png",
            LIVEPROXY_IMAGE_ALT,
        ),
    )

    for target, title, description, image_path, image_alt in cases:
        page = client.get("/login", params={"next": target})
        assert page.status_code == 200
        assert f"<title>{LOGIN_TITLE}</title>" in page.text
        assert '<link rel="canonical" href="http://testserver/login">' in page.text
        assert f'<meta property="og:title" content="{title}">' in page.text
        assert f'<meta property="og:description" content="{description}">' in page.text
        assert (
            f'<meta property="og:url" content="http://testserver{target}">'
            in page.text
        )
        assert (
            f'<meta property="og:image" content="http://testserver{image_path}">'
            in page.text
        )
        assert (
            f'<meta name="twitter:image" content="http://testserver{image_path}">'
            in page.text
        )
        assert f'<meta name="twitter:image:alt" content="{image_alt}">' in page.text

        structured_data = _structured_data(page)
        assert structured_data["name"] == LOGIN_TITLE
        assert structured_data["url"] == f"http://testserver{target}"
        assert structured_data["image"] == f"http://testserver{image_path}"


@pytest.mark.parametrize(
    "unsafe_next",
    (
        "//evil.example/manager",
        "https://evil.example/manager",
        "\\\\evil.example\\manager",
        "manager",
    ),
)
def test_login_preview_ignores_unsafe_next_paths(client, unsafe_next):
    client.headers.pop("X-API-Key")

    page = client.get("/login", params={"next": unsafe_next})

    assert page.status_code == 200
    assert '<meta property="og:title" content="Iniciar sesión">' in page.text
    assert f'<meta name="description" content="{LOGIN_DESCRIPTION}">' in page.text
    assert '<meta property="og:url" content="http://testserver/login">' in page.text
    assert (
        '<meta property="og:image" content="http://testserver/static/'
        'og-twitch-tools.png">' in page.text
    )
    assert "evil.example" not in page.text


def test_canonical_and_social_urls_use_configured_public_origin(client, monkeypatch):
    client.headers.pop("X-API-Key")
    monkeypatch.setenv("TWITCH_M3U_PUBLIC_ORIGIN", "https://m3u.example.com/")
    monkeypatch.setenv("TWITCH_M3U_TWITTER_HANDLE", "@twitchm3u")

    page = client.get(
        "/login?next=%2Fmanager%2Fp%2Fdemo", headers={"Host": "internal:8000"}
    )

    assert page.status_code == 200
    assert '<link rel="canonical" href="https://m3u.example.com/login">' in page.text
    assert (
        '<meta property="og:url" content="https://m3u.example.com/manager/p/demo">'
        in page.text
    )
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
    structured_data = _structured_data(page)
    assert structured_data["url"] == "https://m3u.example.com/manager/p/demo"
    assert structured_data["image"] == "https://m3u.example.com/static/og-image.png"


def test_public_origin_must_be_an_origin_without_path(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TWITCH_M3U_PUBLIC_ORIGIN", "https://example.com/path")

    with pytest.raises(ValueError, match="absolute HTTP\\(S\\) origin"):
        get_settings()


def test_api_docs_keeps_the_default_swagger_metadata(client):
    page = client.get("/docs")

    assert page.status_code == 200
    assert 'property="og:' not in page.text
    assert 'name="twitter:' not in page.text
