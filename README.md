# Twitch M3U Manager

A small web application for managing M3U playlists of Twitch channels. Each
managed channel is resolved to its highest-quality available HLS stream when
the playlist is downloaded or requested. Twitch stream URLs expire, so the
application stores channel identities—not expiring URLs—and refreshes them for
every export.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>. The interactive API is at <http://localhost:8000/docs>.
Run tests with `pip install -r requirements-dev.txt && pytest`.

## Playlists

- Create playlists and add or remove Twitch channels in the web interface.
- Import an M3U file. Direct HTTP(S) stream URLs are retained as static entries.
- Live status is only checked when channels are added or an M3U is exported;
  opening a playlist page makes no Twitch status requests. Offline channels
  remain saved but are omitted from exports.
- Download or subscribe to `/m3u/{name}.m3u`; each live managed channel is
  freshly extracted and its highest-quality variant is selected.
- If Twitch's live-status check fails, or a live stream cannot be extracted,
  the request returns a clear error instead of a partial playlist.
- Live checks are batched in small groups and briefly cached to reduce Twitch
  API load; Twitch HTTP 429 responses are passed through with `Retry-After`
  guidance instead of being reported as a generic gateway error.

Playlist metadata is stored as JSON under `data/`. Set
`TWITCH_M3U_DATA_DIR` to use another directory. Optional HTTP Basic
authentication is enabled when both `TWITCH_M3U_AUTH_USER` and
`TWITCH_M3U_AUTH_PASSWORD` are set. `/health` remains unauthenticated.

## Migrate existing sample playlists

To convert an existing directory of M3U files, run:

```sh
python tools/migrate_legacy.py /path/to/legacy/data
```

The idempotent migration keeps playlist names, converts recognized legacy
Twitch channel entries to managed channels, retains non-proxy direct URLs, and
does not copy unrecognized proxy command URLs. Existing destinations are never
overwritten.

## Docker

See [DOCKER.md](DOCKER.md) or run `docker compose up --build -d`.
