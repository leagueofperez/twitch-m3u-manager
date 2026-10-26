import os
import unittest
from unittest.mock import patch

import shortener
from shortener import ShortenerError


class ShortenerTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"SHORT_IO_API_KEY": "test-key"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_issued_signature_accepts_original_data(self):
        issued = shortener.issue(
            "https://example.test/master.m3u8?token=secret",
            "channel-720p60",
            "Twitch channel 720p60",
        )

        self.assertTrue(
            shortener.verify(
                issued["ts"],
                "https://example.test/master.m3u8?token=secret",
                issued["slug"],
                issued["title"],
                issued["sig"],
            )
        )

    def test_signature_rejects_tampering_and_invalid_timestamps(self):
        issued = shortener.issue("https://example.test/stream", "slug", "title")

        self.assertFalse(
            shortener.verify(
                issued["ts"], "https://example.test/other", "slug", "title", issued["sig"]
            )
        )
        self.assertFalse(shortener.verify([], "url", "slug", "title", "sig"))

    @patch("shortener._request")
    def test_invalid_signature_is_rejected_before_external_request(self, request):
        with self.assertRaises(ShortenerError):
            shortener.shorten(
                "https://example.test/stream", "slug", "title", 1, "invalid"
            )

        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
