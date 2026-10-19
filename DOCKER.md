# Docker deployment

Build and start the application with Docker Compose:

```sh
docker compose up --build -d
```

The web UI is available at `http://localhost:8000`. Playlist metadata is stored
in `./data` and survives container replacement. Set
`TWITCH_M3U_AUTH_USER` and `TWITCH_M3U_AUTH_PASSWORD` in the environment to
enable HTTP Basic authentication; use HTTPS when exposing the app publicly.
Set `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` to the credentials of a
Twitch developer application so the app can use the official Helix API for
live-channel checks.

To run the container without Compose:

```sh
docker build -t twitch-m3u-manager .
docker run --rm -p 8000:8000 \
  -e TWITCH_CLIENT_ID \
  -e TWITCH_CLIENT_SECRET \
  -v "$PWD/data:/app/data" twitch-m3u-manager
```
