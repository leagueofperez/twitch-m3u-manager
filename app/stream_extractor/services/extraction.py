import shortener
from twitch import extract_streams_for_target, parse_twitch_url


def extract_streams(url):
    is_live, target = parse_twitch_url(url)
    streams = extract_streams_for_target(is_live, target)

    if shortener.is_enabled():
        for stream in streams:
            quality = stream["quality"]
            stream["shorten"] = shortener.issue(
                stream["url"],
                shortener.slug_for(is_live, target, quality),
                shortener.title_for(is_live, target, quality),
            )

    return streams
