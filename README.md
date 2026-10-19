# Twitch M3U Manager

A small web application for managing M3U playlists of Twitch channels. Each
managed channel is resolved to its highest-quality available HLS stream when
the playlist is downloaded or requested. Twitch stream URLs expire, so the
application stores channel identities—not expiring URLs—and refreshes them for
every export.

## Twitch authentication

The app uses Twitch's official Helix API to check whether channels are live.
It authenticates server-to-server with an OAuth app access token, so no Twitch
user login or user authorization is needed. No OAuth redirect URL is required;
the app uses the client-credentials flow. Configure these environment variables:

| Variable | Description |
| --- | --- |
| `TWITCH_CLIENT_ID` | Client ID for your Twitch developer application |
| `TWITCH_CLIENT_SECRET` | Client secret for that application; keep it private |

To obtain them, sign in to the [Twitch Developer Console](https://dev.twitch.tv/console/apps),
register an application, then copy its Client ID and generate/copy its Client
Secret from the application settings. Do not commit the secret to source
control or share it publicly.

Load these variables into the environment of the process that runs the app.
For example, in a local shell:

```sh
export TWITCH_CLIENT_ID="your-client-id"
export TWITCH_CLIENT_SECRET="your-client-secret"
export TWITCH_M3U_LOGIN_USERNAME="admin"
export TWITCH_M3U_LOGIN_PASSWORD="choose-a-strong-password-at-least-12-chars"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For Docker Compose, put the same variable names in a `.env` file beside
`docker-compose.yml`; Compose reads it automatically:

Start from the complete example (`cp .env.example .env`), then fill in the
Twitch developer credentials and a strong login username/password there.

Keep `.env` out of version control. The app exchanges the Twitch developer
credentials for an app access token and caches it until shortly before it
expires. Helix handles live-status checks; playback-token extraction still
uses Twitch's existing GraphQL/Usher flow to preserve HLS playlist exports.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit credentials; set TWITCH_M3U_COOKIE_SECURE=false for local HTTP
./start.sh
```

Open <http://localhost:8000>. The interactive API is at <http://localhost:8000/docs>.
`start.sh` loads `.env`; if you run Uvicorn directly, export the variables
yourself first. Use HTTPS in deployments and leave the secure-cookie setting
enabled. Run tests with `pip install -r requirements-dev.txt && pytest`.

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

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TWITCH_CLIENT_ID` | — | Twitch developer application client ID (required for live checks) |
| `TWITCH_CLIENT_SECRET` | — | Twitch developer application secret (required for live checks) |
| `TWITCH_M3U_LOGIN_USERNAME` | — | Required browser-login username; startup creates or updates this account |
| `TWITCH_M3U_LOGIN_PASSWORD` | — | Required browser-login password; minimum 12 characters |
| `TWITCH_M3U_DATA_DIR` | `data/` | Directory for playlist JSON |
| `TWITCH_M3U_AUTH_DB` | `<data-dir>/auth.sqlite3` | SQLite database for API keys and browser sessions |
| `TWITCH_M3U_COOKIE_SECURE` | `true` | Send browser-session cookies only over HTTPS; set to `false` only for local HTTP |
| `PORT` | `8000` | Listening port in `start.sh` and host port in Docker Compose |

Set the Twitch and login variables before starting the app. The login
credentials are required; `.env.example` lists all supported variables.
The browser username must be 1–100 printable characters. Passwords are
stored as salted, slow hashes; changing the configured password invalidates
existing browser sessions. The SQLite database contains API-key hashes and
sessions, not plaintext API keys; keep it on persistent storage and restrict
access to it.

Use the username/password login at `/login` for the browser UI. For external
API clients, use API keys: read-only keys can list playlists, view playlist
details, and download M3U files; read-write keys can also create, import, edit,
and delete playlists. API keys can be sent with the `X-API-Key` header or as a
Bearer token. Only `/health`, the login page, and login/logout routes are
available without authentication; static UI assets are also public. The docs
and OpenAPI schema require authentication. Create or revoke keys from the
repository root:

```sh
python -m app.auth_cli create --name owner --role read-write
python -m app.auth_cli create --name player --role read-only
python -m app.auth_cli list
python -m app.auth_cli revoke <key-id>
```

The CLI defaults to `data/auth.sqlite3`, matching the app's default. If you
override `TWITCH_M3U_AUTH_DB`, pass the same path with `--db` or export that
variable in the shell before running the CLI.

The CLI displays a new key only once. Use it in API calls with the
`X-API-Key: <key>` header or `Authorization: Bearer <key>`. Browser login
creates a 12-hour, HttpOnly session cookie; session-authenticated writes are
restricted to same-origin requests. M3U players that cannot set headers may
instead use `/m3u/{name}.m3u?apiKey=<key>` for downloads. Query-string keys can
appear in browser history, proxy/access logs, and monitoring systems; prefer
headers where possible and use HTTPS.

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
