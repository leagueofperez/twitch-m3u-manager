import unittest
from unittest.mock import Mock, patch

import twitch_extractor
from twitch import (
    TwitchError,
    extract_streams_from_url,
    extract_streams_for_target,
    parse_master_m3u8,
    parse_twitch_url,
    quality_score,
)


class TwitchExtractorTests(unittest.TestCase):
    def test_legacy_module_reexports_package_api(self):
        self.assertIs(twitch_extractor.TwitchError, TwitchError)
        self.assertIs(twitch_extractor.parse_twitch_url, parse_twitch_url)
        self.assertIs(twitch_extractor.parse_master_m3u8, parse_master_m3u8)

    def test_parse_twitch_channel_and_vod_inputs(self):
        self.assertEqual(parse_twitch_url("admiralbulldog"), (True, "admiralbulldog"))
        self.assertEqual(
            parse_twitch_url("https://www.twitch.tv/videos/2899093597"),
            (False, "2899093597"),
        )

    def test_parse_rejects_non_twitch_hosts(self):
        with self.assertRaises(TwitchError):
            parse_twitch_url("https://example.com/channel")

    def test_quality_sort_key_orders_quality_and_audio(self):
        self.assertGreater(quality_score("1080p60"), quality_score("720p60"))
        self.assertEqual(quality_score("audio_only"), 0)

    @patch("twitch.extraction.extract_streams_for_target")
    def test_url_wrapper_parses_once_and_delegates(self, extract):
        extract.return_value = [{"quality": "720p60", "url": "https://example.test/a"}]

        result = extract_streams_from_url("twitch.tv/channel")

        self.assertEqual(result, extract.return_value)
        extract.assert_called_once_with(True, "channel")

    @patch("twitch.manifest.requests.get")
    def test_master_playlist_resolves_relative_stream_urls(self, get):
        response = Mock()
        response.text = (
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=123,RESOLUTION=1280x720,'
            'FRAME-RATE=60.000\n'
            "720p60/index.m3u8\n"
        )
        get.return_value = response

        streams = parse_master_m3u8("https://example.test/path/master.m3u8?token=x")

        self.assertEqual(
            streams,
            {"720p60": {"url": "https://example.test/path/720p60/index.m3u8"}},
        )
        get.assert_called_once()

    @patch("twitch.extraction.fetch_playback_token", return_value=("token", "sig", None))
    @patch(
        "twitch.extraction.parse_master_m3u8",
        return_value={"720p60": {"url": "https://example.test/stream"}},
    )
    def test_target_extraction_returns_quality_urls(self, _manifest, _token):
        self.assertEqual(
            extract_streams_for_target(True, "channel"),
            [{"quality": "720p60", "url": "https://example.test/stream"}],
        )


if __name__ == "__main__":
    unittest.main()
