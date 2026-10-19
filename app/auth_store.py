"""SQLite storage for API keys and browser sessions."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

API_KEY_PREFIX = "tmm_"
SESSION_TTL_SECONDS = 12 * 60 * 60
PASSWORD_ITERATIONS = 600_000
_DUMMY_PASSWORD_SALT = bytes.fromhex("6a2b82af8b60d4a6c40f3ca485cd0631")
_DUMMY_PASSWORD_HASH = hashlib.pbkdf2_hmac(
    "sha256", b"not-a-valid-password", _DUMMY_PASSWORD_SALT, PASSWORD_ITERATIONS
).hex()


@dataclass(frozen=True)
class APIKey:
    id: str
    name: str
    role: str


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        os.chmod(db_path, 0o600)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(db_path: Path) -> None:
    with _connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK (role IN ('read-only', 'read-write')),
                created_at INTEGER NOT NULL,
                revoked_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_iterations INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL REFERENCES users(username),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
            """
        )
        session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "username" not in session_columns:
            connection.execute("DROP TABLE sessions")
            connection.execute(
                """
                CREATE TABLE sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at)"
            )


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _password_hash(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str, iterations: int) -> bool:
    try:
        candidate = _password_hash(password, bytes.fromhex(salt_hex), iterations)
    except ValueError:
        return False
    return secrets.compare_digest(candidate, hash_hex)


def bootstrap_user(db_path: Path, username: str, password: str) -> None:
    clean_username = username.strip()
    if (
        not clean_username
        or len(clean_username) > 100
        or any(not character.isprintable() for character in clean_username)
    ):
        raise ValueError("login username must be 1-100 printable characters")
    if len(password) < 12:
        raise ValueError("login password must be at least 12 characters")

    initialize(db_path)
    with _connect(db_path) as connection:
        existing = connection.execute(
            """SELECT password_salt, password_hash, password_iterations
               FROM users WHERE username = ?""",
            (clean_username,),
        ).fetchone()
        if existing and _verify_password(
            password,
            existing["password_salt"],
            existing["password_hash"],
            existing["password_iterations"],
        ):
            connection.execute(
                "DELETE FROM sessions WHERE username <> ?", (clean_username,)
            )
            connection.execute(
                "DELETE FROM users WHERE username <> ?", (clean_username,)
            )
            return

        salt = secrets.token_bytes(16)
        password_hash = _password_hash(password, salt, PASSWORD_ITERATIONS)
        connection.execute(
            """INSERT INTO users
               (username, password_salt, password_hash, password_iterations, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                 password_salt = excluded.password_salt,
                 password_hash = excluded.password_hash,
                 password_iterations = excluded.password_iterations,
                 updated_at = excluded.updated_at""",
            (
                clean_username,
                salt.hex(),
                password_hash,
                PASSWORD_ITERATIONS,
                int(time.time()),
            ),
        )
        connection.execute("DELETE FROM sessions WHERE username = ?", (clean_username,))
        connection.execute("DELETE FROM sessions WHERE username <> ?", (clean_username,))
        connection.execute("DELETE FROM users WHERE username <> ?", (clean_username,))


def verify_user(db_path: Path, username: str, password: str) -> bool:
    if not username or len(username) > 100 or len(password) > 1024:
        return False
    with _connect(db_path) as connection:
        row = connection.execute(
            """SELECT password_salt, password_hash, password_iterations
               FROM users WHERE username = ?""",
            (username,),
        ).fetchone()
    if row is None:
        _verify_password(
            password,
            _DUMMY_PASSWORD_SALT.hex(),
            _DUMMY_PASSWORD_HASH,
            PASSWORD_ITERATIONS,
        )
        return False
    return _verify_password(
        password,
        row["password_salt"],
        row["password_hash"],
        row["password_iterations"],
    )


def create_api_key(db_path: Path, name: str, role: str) -> tuple[APIKey, str]:
    if role not in {"read-only", "read-write"}:
        raise ValueError("role must be read-only or read-write")
    clean_name = name.strip()
    if (
        not clean_name
        or len(clean_name) > 100
        or any(not character.isprintable() for character in clean_name)
    ):
        raise ValueError("key name must be 1-100 printable characters")

    initialize(db_path)
    key_id = str(uuid.uuid4())
    plaintext = API_KEY_PREFIX + secrets.token_urlsafe(32)
    with _connect(db_path) as connection:
        connection.execute(
            """INSERT INTO api_keys (id, name, key_hash, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (key_id, clean_name, _hash_secret(plaintext), role, int(time.time())),
        )
    return APIKey(key_id, clean_name, role), plaintext


def get_api_key(db_path: Path, plaintext: str) -> APIKey | None:
    if not plaintext or len(plaintext) > 256:
        return None
    with _connect(db_path) as connection:
        row = connection.execute(
            """SELECT id, name, role FROM api_keys
               WHERE key_hash = ? AND revoked_at IS NULL""",
            (_hash_secret(plaintext),),
        ).fetchone()
    return APIKey(row["id"], row["name"], row["role"]) if row else None


def create_session(db_path: Path, username: str) -> tuple[str, int]:
    now = int(time.time())
    expires_at = now + SESSION_TTL_SECONDS
    session_token = secrets.token_urlsafe(32)
    with _connect(db_path) as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            """INSERT INTO sessions (token_hash, username, created_at, expires_at)
               SELECT ?, username, ?, ? FROM users WHERE username = ?""",
            (_hash_secret(session_token), now, expires_at, username),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError("login user no longer exists")
    return session_token, expires_at


def get_session(db_path: Path, session_token: str) -> APIKey | None:
    if not session_token or len(session_token) > 256:
        return None
    now = int(time.time())
    with _connect(db_path) as connection:
        row = connection.execute(
            """SELECT u.username FROM sessions AS s
               JOIN users AS u ON u.username = s.username
               WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (_hash_secret(session_token), now),
        ).fetchone()
    return APIKey(f"user:{row['username']}", row["username"], "read-write") if row else None


def delete_session(db_path: Path, session_token: str) -> None:
    if not session_token or len(session_token) > 256:
        return
    with _connect(db_path) as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (_hash_secret(session_token),),
        )


def revoke_api_key(db_path: Path, key_id: str) -> bool:
    initialize(db_path)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (int(time.time()), key_id),
        )
    return cursor.rowcount == 1


def list_api_keys(db_path: Path) -> list[dict[str, str | int | None]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            """SELECT id, name, role, created_at, revoked_at FROM api_keys
               ORDER BY created_at, id"""
        ).fetchall()
    return [dict(row) for row in rows]
