"""Command-line management for application API keys."""
from __future__ import annotations

import argparse
from pathlib import Path

from .auth_store import create_api_key, list_api_keys, revoke_api_key
from .config import get_settings


def _db_path(value: str | None) -> Path:
    settings = get_settings()
    return Path(value).resolve() if value else settings.auth_db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Twitch M3U Manager API keys")
    parser.add_argument(
        "--db",
        help="SQLite path (defaults to TWITCH_M3U_AUTH_DB or data/auth.sqlite3)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="Create a new API key")
    create.add_argument("--name", required=True)
    create.add_argument(
        "--role", choices=("read-only", "read-write"), required=True
    )

    revoke = commands.add_parser("revoke", help="Revoke an API key by ID")
    revoke.add_argument("key_id")

    commands.add_parser("list", help="List API keys without revealing their secrets")

    args = parser.parse_args()
    db_path = _db_path(args.db)
    if args.command == "create":
        key, plaintext = create_api_key(db_path, args.name, args.role)
        print(f"Key ID: {key.id}")
        print(f"Name: {key.name}")
        print(f"Role: {key.role}")
        print(f"API key (shown once): {plaintext}")
    elif args.command == "revoke":
        if not revoke_api_key(db_path, args.key_id):
            parser.error(f"active API key not found: {args.key_id}")
        print(f"Revoked API key: {args.key_id}")
    else:
        for key in list_api_keys(db_path):
            state = "revoked" if key["revoked_at"] else "active"
            print(
                f'{key["id"]}\t{key["name"]}\t{key["role"]}\t{state}\t'
                f'{key["created_at"]}'
            )


if __name__ == "__main__":
    main()
