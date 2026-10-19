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

Sign in to the web UI with the configured username and password. Create API
keys separately for API clients:

```sh
docker compose exec twitch-m3u-manager \
  python -m app.auth_cli create --name owner --role read-write
```

The command prints the API key once. Save it securely. Create read-only keys
with `--role read-only`; list or revoke keys with `python -m app.auth_cli list`
or `python -m app.auth_cli revoke <key-id>` inside the container.

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
