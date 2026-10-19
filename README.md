# Twitch M3U Manager

A small web application for managing M3U playlists of Twitch channels. Each
managed channel is resolved to its highest-quality available HLS stream when
the playlist is downloaded or requested. Twitch stream URLs expire, so the
application stores channel identities—not expiring URLs—and refreshes them for
every export.

## Twitch authentication

The app uses Twitch's official Helix API to check whether channels are live.
It authenticates server-to-server with an OAuth app access token, so no Twitch
user login or user authorization is needed. Configure these environment
variables:

| Variable | Description |
| --- | --- |
| `TWITCH_CLIENT_ID` | Client ID for your Twitch developer application |
| `TWITCH_CLIENT_SECRET` | Client secret for that application; keep it private |

To obtain them, sign in to the [Twitch Developer Console](https://dev.twitch.tv/console/apps),
register an application, then copy its Client ID and generate/copy its Client
Secret from the application settings. Do not commit the secret to source
control or share it publicly.

Load both variables into the environment of the process that runs the app. For
example, in a local shell:

```sh
export TWITCH_CLIENT_ID="your-client-id"
export TWITCH_CLIENT_SECRET="your-client-secret"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For Docker Compose, put the same variable names in a `.env` file beside
`docker-compose.yml`; Compose reads it automatically:

```dotenv
TWITCH_CLIENT_ID=your-client-id
TWITCH_CLIENT_SECRET=your-client-secret
```

Keep `.env` out of version control. The app exchanges the credentials for an
app access token and caches it until shortly before it expires. Helix handles
live-status checks; playback-token extraction still uses Twitch's existing
GraphQL/Usher flow to preserve HLS playlist exports.

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

Live-channel checks use Twitch's official Helix API and require a Twitch
developer application's `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in the
environment. The app obtains and caches an app access token using OAuth's
client-credentials flow. Checks query up to 100 channels per Helix request and
split larger checks into additional requests. Playback-token extraction still
uses Twitch's existing GraphQL/Usher flow because Helix does not provide HLS
playback tokens.

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
