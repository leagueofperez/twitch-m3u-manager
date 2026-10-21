# Manage the Twitch M3U Manager Docker stack.
#
# Run `just` with no arguments to list every recipe.
#
# The interactive recipes (shell, auth-cli, sqlite) need a running
# container: run `just up` first.

set shell := ["bash", "-c"]

service := "twitch-m3u-manager"
image := "twitch-m3u-manager"
auth_db := "/app/data/auth.sqlite3"
compose := "docker compose"

# List the available recipes
default:
    @just --list

# Build the image without starting the stack
build:
    {{compose}} build

# Start the stack in the background
up:
    {{compose}} up -d

# Stop the stack and remove its containers
down:
    {{compose}} down

# Show the status of the stack
ps:
    {{compose}} ps

# Rebuild the image and recreate the containers
rebuild:
    {{compose}} up -d --build

# Restart the containers without rebuilding them
restart:
    {{compose}} restart

# Remove containers and networks; preserve ./data
clean:
    {{compose}} down --remove-orphans
    docker image rm {{image}} 2>/dev/null || true

# Follow the application logs
logs:
    {{compose}} logs -f

# Open a bash shell inside the running container
shell:
    {{compose}} exec {{service}} bash

# Manage users and API keys with the interactive CLI
auth-cli:
    {{compose}} exec {{service}} python -m app.auth_cli

# Open a SQLite shell on the authentication database
sqlite:
    {{compose}} exec {{service}} sqlite3 {{auth_db}}
