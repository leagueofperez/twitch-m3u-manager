"""Interactive command-line management for application users and API keys."""
from __future__ import annotations

import getpass
import sqlite3
import sys
from pathlib import Path
from typing import Callable

from .auth_store import (
    KEY_KINDS,
    PRIVATE,
    PUBLIC,
    create_api_key,
    create_user,
    delete_user,
    initialize,
    list_api_keys,
    list_users,
    revoke_api_key,
    update_api_key,
    update_user_password,
)
from .config import get_settings

KIND_DESCRIPTIONS = {
    PUBLIC: "Public key - read only, safe to share (for example with a player).",
    PRIVATE: "Private key - read and write, DO NOT SHARE.",
}


def _choose(prompt: str, choices: tuple[str, ...]) -> str:
    options = "/".join(choices)
    while True:
        value = input(f"{prompt} ({options}): ").strip().lower()
        if value in choices:
            return value
        print(f"Choose one of: {options}.")


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N]: ").strip().lower() in {"y", "yes"}


def _run_action(action: Callable[[], None]) -> None:
    try:
        action()
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Error: {exc}")


def _select_database(db_path: Path) -> Path:
    while True:
        print(f"\nAuth database: {db_path}")
        value = input("Enter a different database path, or press Enter to keep it: ")
        if not value.strip():
            return db_path
        selected = Path(value.strip()).expanduser().resolve()
        try:
            initialize(selected)
        except (OSError, sqlite3.Error) as exc:
            print(f"Could not open database: {exc}")
            continue
        print(f"Using auth database: {selected}")
        return selected


def _show_users(db_path: Path) -> None:
    usernames = list_users(db_path)
    if not usernames:
        print("No users found.")
        return
    print("Users:")
    for username in usernames:
        print(f"  {username}")


def _create_user(db_path: Path) -> None:
    username = input("Username: ")
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Error: passwords do not match.")
        return
    username, api_key = create_user(db_path, username, password)
    print(f"Created user: {username}")
    print(f"Default private API key (shown once): {api_key}")
    print(KIND_DESCRIPTIONS[PRIVATE])


def _change_user_password(db_path: Path) -> None:
    username = input("Username: ").strip()
    password = getpass.getpass("New password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        print("Error: passwords do not match.")
        return
    if not update_user_password(db_path, username, password):
        print(f"User not found: {username}")
        return
    print(f"Updated password and revoked active sessions for: {username}")


def _delete_user(db_path: Path) -> None:
    username = input("Username to delete: ").strip()
    if not _confirm(f"Delete user {username!r} and revoke their API keys?"):
        print("Canceled.")
        return
    if not delete_user(db_path, username):
        print(f"User not found: {username}")
        return
    print(f"Deleted user and revoked their API keys: {username}")


def _users_menu(db_path: Path) -> None:
    while True:
        print("\nUsers")
        print("  1. List users")
        print("  2. Create user")
        print("  3. Update user password")
        print("  4. Delete user")
        print("  0. Back")
        choice = _choose("Select", ("0", "1", "2", "3", "4"))
        if choice == "0":
            return
        actions = {
            "1": lambda: _show_users(db_path),
            "2": lambda: _create_user(db_path),
            "3": lambda: _change_user_password(db_path),
            "4": lambda: _delete_user(db_path),
        }
        _run_action(actions[choice])


def _show_api_keys(db_path: Path, active_only: bool = False) -> None:
    keys = list_api_keys(db_path)
    if active_only:
        keys = [key for key in keys if key["revoked_at"] is None]
    if not keys:
        print("No API keys found.")
        return
    print("API keys (secrets are not shown in this list):")
    for key in keys:
        state = "revoked" if key["revoked_at"] else "active"
        owner = key["owner_username"] or "<unassigned>"
        print(
            f'  {key["id"]} | {key["name"]} | {key["kind"]} | '
            f'{owner} | {state} | created {key["created_at"]}'
        )


def _create_api_key(db_path: Path) -> None:
    name = input("Key name: ")
    print("  public  - read only, safe to share")
    print("  private - read and write, DO NOT SHARE")
    kind = _choose("Kind", KEY_KINDS)
    owner = input("Owner username: ")
    key, plaintext = create_api_key(db_path, name, kind, owner)
    print(f"Created API key: {key.id}")
    print(f"Name: {key.name}")
    print(f"Kind: {key.kind}")
    print(f"Owner: {key.owner_username}")
    print(f"API key (shown once): {plaintext}")
    print(KIND_DESCRIPTIONS[kind])


def _edit_api_key(db_path: Path) -> None:
    _show_api_keys(db_path, active_only=True)
    key_id = input("Active key ID to edit: ").strip()
    key = next(
        (
            item
            for item in list_api_keys(db_path)
            if item["id"] == key_id and item["revoked_at"] is None
        ),
        None,
    )
    if key is None:
        print(f"Active API key not found: {key_id}")
        return

    name = input(f'Name [{key["name"]}]: ').strip() or str(key["name"])
    kind = input(
        f'Kind [{key["kind"]}] ({" / ".join(KEY_KINDS)}): '
    ).strip().lower()
    if not kind:
        kind = str(key["kind"])
    if kind not in KEY_KINDS:
        print(f"Error: kind must be one of: {' / '.join(KEY_KINDS)}.")
        return
    current_owner = key["owner_username"]
    owner_prompt = current_owner or "<unassigned>"
    owner_input = input(
        f"Owner username [{owner_prompt}] (Enter keeps, - unassigns): "
    ).strip()
    if owner_input == "-":
        owner = None
    else:
        owner = owner_input or current_owner
    if not update_api_key(db_path, key_id, name, kind, owner):
        print(f"Active API key not found: {key_id}")
        return
    print(f"Updated API key metadata: {key_id}")
    print(KIND_DESCRIPTIONS[kind])


def _revoke_api_key(db_path: Path) -> None:
    _show_api_keys(db_path, active_only=True)
    key_id = input("Active key ID to revoke: ").strip()
    if not _confirm(f"Revoke API key {key_id!r}?"):
        print("Canceled.")
        return
    if not revoke_api_key(db_path, key_id):
        print(f"Active API key not found: {key_id}")
        return
    print(f"Revoked API key: {key_id}")


def _api_keys_menu(db_path: Path) -> None:
    while True:
        print("\nAPI keys")
        print("  1. List keys")
        print("  2. Create key")
        print("  3. Edit key name, kind, or owner")
        print("  4. Revoke key")
        print("  0. Back")
        choice = _choose("Select", ("0", "1", "2", "3", "4"))
        if choice == "0":
            return
        actions = {
            "1": lambda: _show_api_keys(db_path),
            "2": lambda: _create_api_key(db_path),
            "3": lambda: _edit_api_key(db_path),
            "4": lambda: _revoke_api_key(db_path),
        }
        _run_action(actions[choice])


def main() -> None:
    if len(sys.argv) > 1:
        print("This is an interactive CLI and does not accept command-line arguments.")
        return

    db_path = get_settings().auth_db_path
    try:
        initialize(db_path)
        db_path = _select_database(db_path)
        while True:
            print("\nTwitch M3U Manager - user and API-key management")
            print("  1. Manage users")
            print("  2. Manage API keys")
            print("  3. Change auth database")
            print("  0. Exit")
            choice = _choose("Select", ("0", "1", "2", "3"))
            if choice == "0":
                print("Goodbye.")
                return
            if choice == "1":
                _users_menu(db_path)
            elif choice == "2":
                _api_keys_menu(db_path)
            else:
                db_path = _select_database(db_path)
    except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
    except (OSError, sqlite3.Error) as exc:
        print(f"Could not open auth database: {exc}")


if __name__ == "__main__":
    main()
