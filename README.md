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
enabled. For a trusted reverse proxy, forward the original `Host` and
`X-Forwarded-Proto` headers and set `FORWARDED_ALLOW_IPS` to the proxy's IP or
CIDR so Uvicorn can safely recognize the external HTTPS scheme. Do not set it
to `*` if clients can reach the app directly. Run tests with
`pip install -r requirements-dev.txt && pytest`.

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
| `TWITCH_M3U_PUBLIC_ORIGIN` | Request origin | Public HTTP(S) origin used for canonical and social metadata URLs, e.g. `https://m3u.example.com` |
| `TWITCH_M3U_TWITTER_HANDLE` | — | Optional X/Twitter account handle, including `@`, used for social attribution |
| `PORT` | `8000` | Listening port in `start.sh` and host port in Docker Compose |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Trusted proxy addresses for Uvicorn's forwarded-header support |

Set the Twitch and login variables before starting the app. The login
credentials are required; `.env.example` lists all supported variables.
The browser username must be 1–100 printable characters. Passwords are
stored as salted, slow hashes; changing the configured password invalidates
existing browser sessions. The SQLite database contains API-key hashes and
sessions, not plaintext API keys; keep it on persistent storage and restrict
access to it.

**Login troubleshooting:** the login form submits credentials by `POST` in
the request body, never in the URL. If login succeeds but redirects back to
`/login?next=/`, the browser likely did not send the session cookie. For plain
HTTP on a trusted local network only, set `TWITCH_M3U_COOKIE_SECURE=false`;
otherwise serve the app over HTTPS and keep it `true`. Behind a reverse proxy,
configure `FORWARDED_ALLOW_IPS` for the proxy and preserve the original `Host`
and `X-Forwarded-Proto` headers; otherwise same-origin validation may reject
the login or secure-cookie behavior may not match the external URL.

Use the username/password login at `/login` for the browser UI. The configured
environment account is created or updated at startup. If it has no active
default key, startup creates a private API key and prints it once to the
application log. Protect these logs like credentials and copy the key to a
secret manager; it is not stored in plaintext and will not be shown again.
Manage users and API keys with the interactive CLI:

```sh
python -m app.auth_cli
```

The menu supports listing, creating, password-updating, and deleting users.
Passwords are entered securely; changing one invalidates the user's active
browser sessions. Deleting a user revokes their API keys and removes their
sessions. Creating a user also creates a default private API key and
displays it once. Protect the output and save the key securely.

## API keys: public and private

Every API key is either **public** or **private**:

| Kind | Secret prefix | Permissions | Use |
| --- | --- | --- | --- |
| `public` | `tmm_pub_` | Read only: list playlists, view details, download M3U files | Safe to share, for example with an IPTV player |
| `private` | `tmm_priv_` | Read and write: create, import, edit, and delete playlists | Never share; use it only in request headers |

The secret prefix shows the kind of a key at a glance, so a leaked key can be
classified without looking it up. The key's kind determines its permissions;
the owner is recorded for attribution and key management. The CLI can create
keys of either kind, list key metadata, edit an active key's name, kind, or
owner, and revoke keys. Existing key secrets are not retrievable; newly
created secrets are displayed only once.

Keys created before the ownership feature are assigned to the configured
environment user when the app starts. Deleting a user revokes their keys and
removes active browser sessions. To replace a lost user key, create another
key with the CLI; to replace a lost startup key, revoke it and restart the app
so startup generates and prints a new default key.

Databases created by earlier versions are migrated automatically on startup:
the old `read-only` role becomes `public` and the old `read-write` role
becomes `private`. Key hashes are preserved, so every previously issued secret
keeps working and only its permissions change.

API keys can be sent with the `X-API-Key` header or as a Bearer token. The
following routes are available without authentication: `/health`, the API
documentation (`/docs` and `/openapi.json`), the login page, and the
login/logout routes. Static UI assets are also public. Every other endpoint,
including the browser UI, requires a key or an active session.

The documentation is public, but the actions it describes are not: the
OpenAPI schema marks every protected operation with its security
requirement, so the Swagger UI shows an **Authorize** button. Paste a
private key there to try the endpoints; without a key they answer `401`.

The CLI defaults to the app's configured auth database:
`TWITCH_M3U_AUTH_DB`, or `<data-dir>/auth.sqlite3` when unset. At startup, the
menu lets you keep that database or select another SQLite path.

The CLI displays a new key only once. Use it in API calls with the
`X-API-Key: <key>` header or `Authorization: Bearer <key>`. Browser login
creates a 12-hour, HttpOnly session cookie; session-authenticated writes are
restricted to same-origin requests. M3U players that cannot set headers may
instead use `/m3u/{name}.m3u?apiKey=<key>` for downloads, but only with a
**public** key: private keys sent in a query string are rejected with
`403 Forbidden`, because query strings end up in browser history, proxy and
access logs, and monitoring systems.

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

See [DOCKER.md](DOCKER.md) or run `docker compose up --build -d`. A `justfile`
wraps the common tasks (`just up`, `just down`, `just status`, `just rebuild`,
`just logs`, `just shell`, `just auth-cli`, `just sqlite`); run `just` to list
them all. The image ships a healthcheck that polls the public `/health`
endpoint, so `just status` reports the container as `healthy` or `unhealthy`.
