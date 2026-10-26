# Docker deployment

Build and start the application with Docker Compose:

```sh
docker compose up --build -d
```

A `justfile` wraps the common tasks. Run `just` to list them:

| Recipe | What it does |
| --- | --- |
| `just up` | Start the stack in the background |
| `just down` | Stop the stack and remove its containers |
| `just status` | Show the status of the stack |
| `just rebuild` | Rebuild the image and recreate the containers |
| `just restart` | Restart the containers without rebuilding them |
| `just build` | Build the image without starting the stack |
| `just clean` | Remove the containers, networks and the local image; `./data` is preserved |
| `just logs` | Follow the application logs |
| `just shell` | Open a bash shell inside the running container |
| `just auth-cli` | Run the interactive user and API key management CLI |
| `just sqlite` | Open a SQLite shell on `/app/data/auth.sqlite3` |

The interactive recipes need a running container, so run `just up` first.

The image declares a `HEALTHCHECK` that polls the public `/health` endpoint
every 30 seconds, with a 15-second grace period after startup and 3 retries
before a container is marked unhealthy. `just status` shows the result in the
`STATUS` column, and `docker inspect --format '{{json .State.Health}}'
twitch-m3u-manager` shows the individual probe results. The check uses the
Python interpreter already present in the image, so no extra package is
installed.

The landing page is available at `http://localhost:8000`; the M3U Manager,
Stream Extractor and LiveProxy are at `/manager`, `/extractor` and `/liveproxy`.
One gateway container runs the two internal workers; only port 8000 is
published. Their internal ports 5000 and 53422 are bound to loopback and must
not be published. Playlist metadata is stored in `./data` and survives
container replacement. Set
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

All app interfaces (except the public landing/login) and functional endpoints
require the shared browser session or an API key. The original M3U API remains
at `/api` and `/m3u`. The Extractor's
`/extractor/extract` accepts public or private API keys; the URL-shortening
mutation requires a private key. LiveProxy only accepts private API keys or a
browser session and validates the command as a Twitch channel Streamlink
request. External media clients must send `X-API-Key` or a Bearer token on
every LiveProxy request; private keys are never accepted in query strings.
Clients unable to send authentication headers cannot use the protected
LiveProxy endpoint directly.

The common launcher supervises the FastAPI gateway, Gunicorn Extractor and
LiveProxy processes. The container healthcheck verifies the public gateway and
both internal listeners.

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
app creates a private key and prints it once to the container logs:

```sh
docker compose logs twitch-m3u-manager
```

Treat logs containing a generated key as secrets and store the key securely.
Private keys can read and write playlists and must not be shared; create a
public key (`tmm_pub_`, read only) for players and other shareable clients.
The CLI is an interactive menu for managing users and API keys. If the
container was created before the menu-driven CLI was added, rebuild and
recreate it from the updated source first:

```sh
docker compose up -d --build
```

Then run the menu with an interactive terminal:

```sh
just auth-cli
```

or, without `just`:

```sh
docker exec -it twitch-m3u-manager python -m app.auth_cli
```

The menu defaults to the same auth database mounted at `./data/auth.sqlite3`
and allows selecting another SQLite database path. It supports listing,
creating, updating passwords for, and deleting users, along with creating,
listing, editing, and revoking API keys. Keys come in two kinds: public
(`tmm_pub_`, read only, safe to share) and private (`tmm_priv_`, read and
write, never share). Password prompts do not echo input; new API-key secrets
are displayed only once. Deleting a user revokes that user's keys and active
sessions.

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
