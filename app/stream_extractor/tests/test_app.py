import json
import re
import unittest
from unittest.mock import patch

from app import create_app
from twitch.errors import TwitchError


STREAMS = [
    {
        "quality": "720p60",
        "url": "https://example.test/master.m3u8?token=secret",
    }
]


class AppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_home_page_is_server_rendered_and_has_a_post_form(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<form id="extractForm" method="post"', response.data)
        self.assertIn(b'id="toastMessage"', response.data)
        self.assertIn(b'id="toastDismiss"', response.data)
        self.assertNotIn(b"Requiere JavaScript", response.data)
        self.assertNotIn(b"cdn.jsdelivr.net", response.data)
        self.assertIn(b'<meta name="color-scheme" content="light dark">', response.data)
        self.assertIn(b'data-theme-toggle', response.data)
        self.assertIn(b'class="site-header"', response.data)
        self.assertIn(b'class="site-menu"', response.data)
        self.assertIn(b'class="site-nav-toggle"', response.data)
        self.assertIn(b"src=\"/static/site.js\"", response.data)
        self.assertIn("← Herramientas".encode(), response.data)
        self.assertIn(b"dark:bg-gray-950", response.data)
        css_response = self.client.get("/static/tailwind.generated.css")
        self.assertEqual(css_response.status_code, 200)
        css = css_response.get_data()
        self.assertIn(b".dark\\:bg-gray-950:where(.dark,.dark *)", css)
        self.assertIn(b"@media (prefers-color-scheme:dark)", css)
        self.assertIn(b":root:not([data-theme=light])", css)
        css_response.close()

    def test_shared_theme_assets_are_available_in_standalone_mode(self):
        for asset in ("theme.css", "theme.js", "site.js"):
            with self.subTest(asset=asset):
                response = self.client.get(f"/static/{asset}")

                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 0)
                response.close()

    def test_page_metadata_uses_the_twitch_tools_brand(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("<title>Stream Extractor · Twitch Tools</title>", html)
        self.assertIn('<meta property="og:site_name" content="Twitch Tools">', html)
        self.assertIn('<meta property="og:title" content="Stream Extractor">', html)
        self.assertIn('<meta name="twitter:title" content="Stream Extractor">', html)
        self.assertIn('<meta property="og:url" content="http://localhost/">', html)
        self.assertIn(
            '<meta property="og:image" content="http://localhost/static/og-image.png">',
            html,
        )
        self.assertIn(
            '<meta name="twitter:image" content="http://localhost/static/og-image.png">',
            html,
        )
        self.assertIn(
            '<meta name="twitter:image:alt" content="Stream Extractor: extrae URLs '
            'm3u8 de streams y VODs de Twitch">',
            html,
        )
        self.assertNotIn("Twitch Stream Extractor", html)

        match = re.search(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        structured_data = json.loads(match.group(1))
        self.assertEqual(structured_data["name"], "Stream Extractor")
        self.assertEqual(structured_data["url"], "http://localhost/")
        self.assertEqual(
            structured_data["image"], "http://localhost/static/og-image.png"
        )
        self.assertEqual(structured_data["isPartOf"]["name"], "Twitch Tools")

    def test_page_metadata_uses_the_forwarded_prefix_behind_the_gateway(self):
        response = self.client.get(
            "/",
            headers={
                "X-Forwarded-Prefix": "/extractor",
                "X-Forwarded-Host": "m3u.example.com",
                "X-Forwarded-Proto": "https",
            },
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(
            '<link rel="canonical" href="https://m3u.example.com/extractor/">', html
        )
        self.assertIn(
            '<meta property="og:url" content="https://m3u.example.com/extractor/">',
            html,
        )
        self.assertIn(
            '<meta property="og:image" content="https://m3u.example.com/'
            'extractor/static/og-image.png">',
            html,
        )
        self.assertIn(
            '<meta name="twitter:image" content="https://m3u.example.com/'
            'extractor/static/og-image.png">',
            html,
        )

        match = re.search(
            r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        structured_data = json.loads(match.group(1))
        self.assertEqual(
            structured_data["url"], "https://m3u.example.com/extractor/"
        )
        self.assertEqual(
            structured_data["image"],
            "https://m3u.example.com/extractor/static/og-image.png",
        )

    @patch("services.extraction.extract_streams_for_target", return_value=STREAMS)
    @patch("services.extraction.parse_twitch_url", return_value=(True, "channel"))
    def test_form_post_renders_results_without_javascript(self, parse_url, extract):
        response = self.client.post("/", data={"url": "twitch.tv/channel"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Calidades disponibles", response.data)
        self.assertIn(b"720p60", response.data)
        self.assertIn(b"master.m3u8?token=secret", response.data)
        self.assertIn(b"dark:bg-gray-900", response.data)
        parse_url.assert_called_once_with("twitch.tv/channel")
        extract.assert_called_once_with(True, "channel")

    def test_form_post_renders_validation_error(self):
        response = self.client.post("/", data={"url": "<script>alert(1)</script>"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Error:", response.data)
        self.assertNotIn(b"<script>alert(1)</script>", response.data)

    @patch("services.extraction.extract_streams_for_target", return_value=STREAMS)
    @patch("services.extraction.parse_twitch_url", return_value=(True, "channel"))
    def test_json_extract_contract_is_preserved(self, parse_url, extract):
        response = self.client.post("/extract", json={"url": "twitch.tv/channel"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"streams": STREAMS})
        parse_url.assert_called_once_with("twitch.tv/channel")
        extract.assert_called_once_with(True, "channel")

    def test_extract_rejects_invalid_json_shapes_and_url_types(self):
        cases = (
            (b"[]", "application/json"),
            ({"url": 123}, None),
            ({}, None),
        )

        for payload, content_type in cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/extract", data=payload, content_type=content_type
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_request_body_size_is_limited(self):
        app = create_app({"TESTING": True, "MAX_CONTENT_LENGTH": 32})
        response = app.test_client().post(
            "/extract",
            data=b'{"url":"' + b"a" * 64 + b'"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)

    @patch("app.shortener.shorten")
    @patch("app.shortener.rate_limited", return_value=False)
    @patch("app.shortener.is_enabled", return_value=True)
    def test_shorten_rejects_invalid_types_before_calling_service(
        self, _enabled, _rate_limited, shorten
    ):
        response = self.client.post(
            "/shorten",
            json={
                "url": "https://example.test/master.m3u8",
                "slug": [],
                "title": "title",
                "ts": 1,
                "sig": "signature",
            },
        )

        self.assertEqual(response.status_code, 400)
        shorten.assert_not_called()

    @patch(
        "services.extraction.extract_streams_for_target",
        side_effect=TwitchError("channel offline"),
    )
    @patch("services.extraction.parse_twitch_url", return_value=(True, "channel"))
    def test_json_extract_returns_user_errors_as_400(self, _parse_url, _extract):
        response = self.client.post("/extract", json={"url": "channel"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "channel offline"})

    @patch(
        "services.extraction.extract_streams_for_target",
        side_effect=RuntimeError("unexpected"),
    )
    @patch("services.extraction.parse_twitch_url", return_value=(True, "channel"))
    def test_form_post_reports_internal_errors_with_server_status(
        self, _parse_url, _extract
    ):
        with self.assertLogs("app", level="ERROR"):
            response = self.client.post("/", data={"url": "channel"})

        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Error:", response.data)


if __name__ == "__main__":
    unittest.main()
