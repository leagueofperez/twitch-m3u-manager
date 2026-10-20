# Docker deployment

Build and start the application with Docker Compose:

```sh
docker compose up --build -d
```

The web UI is available at `http://localhost:8000`. Playlist metadata is stored
in `./data` and survives container replacement. Set
`TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` to the credentials of a Twitch
developer application so the app can use the official Helix API for live checks.
API keys and browser sessions are stored in `./data/auth.sqlite3` on the
existing persistent data mount. Copy `.env.example` to `.env`, set the Twitch
credentials and `TWITCH_M3U_LOGIN_USERNAME`/`TWITCH_M3U_LOGIN_PASSWORD`, and
keep `.env` private. The app creates or updates this browser login account when
it starts; use a password of at least 12 characters. For local HTTP development
only, set
`TWITCH_M3U_COOKIE_SECURE=false`; use HTTPS and leave it enabled when deploying
publicly.

For reverse-proxy deployments, forward the original `Host` and
`X-Forwarded-Proto` headers and set `FORWARDED_ALLOW_IPS` in `.env` to the
trusted proxy IP/CIDR (not `*` when the service is directly reachable). The
login form sends credentials in a POST body, never in the URL. If login
returns to `/login?next=/`, verify HTTPS is used with
`TWITCH_M3U_COOKIE_SECURE=true` and that the proxy forwarding settings are
correct. Only set `TWITCH_M3U_COOKIE_SECURE=false` for plain HTTP on a trusted
local network.

Sign in to the web UI with the configured username and password. The configured
account is created or updated at startup. If it has no active default key, the
app creates a read-write key and prints it once to the container logs:

```sh
docker compose logs twitch-m3u-manager
```

Treat logs containing a generated key as secrets and store the key securely.
The CLI is an interactive menu for managing users and API keys. If the
container was created before the menu-driven CLI was added, rebuild and
recreate it from the updated source first:

```sh
docker compose up -d --build
```

Then run the menu with an interactive terminal:

```sh
docker exec -it twitch-m3u-manager python -m app.auth_cli
```

The menu defaults to the same auth database mounted at `./data/auth.sqlite3`
and allows selecting another SQLite database path. It supports listing,
creating, updating passwords for, and deleting users, along with creating,
listing, editing, and revoking API keys. Password prompts do not echo input;
new API-key secrets are displayed only once. Deleting a user revokes that
user's keys and active sessions.

To run the container without Compose:

```sh
docker build -t twitch-m3u-manager .
docker run --rm -p 8000:8000 \
  -e TWITCH_CLIENT_ID \
  -e TWITCH_CLIENT_SECRET \
  -e TWITCH_M3U_LOGIN_USERNAME \
  -e TWITCH_M3U_LOGIN_PASSWORD \
  -v "$PWD/data:/app/data" twitch-m3u-manager
```
