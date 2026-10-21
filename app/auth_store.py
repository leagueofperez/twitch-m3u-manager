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

PUBLIC_KEY_PREFIX = "tmm_pub_"
PRIVATE_KEY_PREFIX = "tmm_priv_"
PUBLIC = "public"
PRIVATE = "private"
KEY_KINDS = (PUBLIC, PRIVATE)
KEY_PREFIXES = {PUBLIC: PUBLIC_KEY_PREFIX, PRIVATE: PRIVATE_KEY_PREFIX}
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
    kind: str
    owner_username: str | None


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
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_iterations INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL CHECK (kind IN ('public', 'private')),
                created_at INTEGER NOT NULL,
                revoked_at INTEGER,
                owner_username TEXT REFERENCES users(username) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS auth_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
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
        _migrate_sessions_table(connection)
        _migrate_api_keys_table(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS api_keys_owner ON api_keys(owner_username)"
        )


def _migrate_sessions_table(connection: sqlite3.Connection) -> None:
    """Drop the legacy session table that referenced API keys by id."""
    session_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "username" in session_columns:
        return
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


def _migrate_api_keys_table(connection: sqlite3.Connection) -> None:
    """Replace the role-based api_keys table with the public/private kind table.

    Existing secrets are copied verbatim, so keys issued before the migration
    keep working: read-only keys become public and read-write keys become
    private.
    """
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(api_keys)").fetchall()
    }
    if "kind" in columns:
        return

    owner_expression = (
        "CASE WHEN owner_username IN (SELECT username FROM users)"
        " THEN owner_username ELSE NULL END"
        if "owner_username" in columns
        else "NULL"
    )
    kind_expression = (
        "CASE WHEN role = 'read-only' THEN 'public' ELSE 'private' END"
        if "role" in columns
        else "'private'"
    )
    connection.executescript(
        f"""
        CREATE TABLE api_keys_kind_migration (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('public', 'private')),
            created_at INTEGER NOT NULL,
            revoked_at INTEGER,
            owner_username TEXT REFERENCES users(username) ON DELETE SET NULL
        );
        INSERT INTO api_keys_kind_migration
            (id, name, key_hash, kind, created_at, revoked_at, owner_username)
        SELECT id, name, key_hash, {kind_expression},
               created_at, revoked_at, {owner_expression}
        FROM api_keys;
        DROP TABLE api_keys;
        ALTER TABLE api_keys_kind_migration RENAME TO api_keys;
        """
    )


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _new_secret(kind: str) -> str:
    """Generate a plaintext secret whose prefix reveals the key kind."""
    return KEY_PREFIXES[kind] + secrets.token_urlsafe(32)


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


def _clean_username(username: str) -> str:
    clean_username = username.strip()
    if (
        not clean_username
        or len(clean_username) > 100
        or any(not character.isprintable() for character in clean_username)
    ):
        raise ValueError("username must be 1-100 printable characters")
    return clean_username


def _clean_key_name(name: str) -> str:
    clean_name = name.strip()
    if (
        not clean_name
        or len(clean_name) > 100
        or any(not character.isprintable() for character in clean_name)
    ):
        raise ValueError("key name must be 1-100 printable characters")
    return clean_name


def _hash_new_password(password: str) -> tuple[str, str]:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    return salt.hex(), _password_hash(password, salt, PASSWORD_ITERATIONS)


def bootstrap_user(db_path: Path, username: str, password: str) -> str | None:
    clean_username = _clean_username(username)

    initialize(db_path)
    with _connect(db_path) as connection:
        existing = connection.execute(
            """SELECT password_salt, password_hash, password_iterations
               FROM users WHERE username = ?""",
            (clean_username,),
        ).fetchone()
        password_matches = bool(
            existing
            and _verify_password(
                password,
                existing["password_salt"],
                existing["password_hash"],
                existing["password_iterations"],
            )
        )
        if not password_matches:
            salt_hex, password_hash = _hash_new_password(password)
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
                    salt_hex,
                    password_hash,
                    PASSWORD_ITERATIONS,
                    int(time.time()),
                ),
            )
            connection.execute(
                "DELETE FROM sessions WHERE username = ?", (clean_username,)
            )
        migration = connection.execute(
            "SELECT value FROM auth_metadata WHERE key = 'api_key_owners_v1'"
        ).fetchone()
        if migration is None:
            connection.execute(
                "UPDATE api_keys SET owner_username = ? WHERE owner_username IS NULL",
                (clean_username,),
            )
            connection.execute(
                """INSERT INTO auth_metadata (key, value)
                   VALUES ('api_key_owners_v1', 'complete')"""
            )
    return ensure_default_api_key(db_path, clean_username)


def ensure_default_api_key(db_path: Path, username: str) -> str | None:
    """Create a user's default private key once; return its plaintext only on creation."""
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """SELECT id FROM api_keys
               WHERE owner_username = ? AND name = 'default'
                 AND kind = 'private' AND revoked_at IS NULL""",
            (username,),
        ).fetchone()
        if existing is not None:
            return None

        key_id = str(uuid.uuid4())
        plaintext = _new_secret("private")
        connection.execute(
            """INSERT INTO api_keys
               (id, name, key_hash, kind, created_at, owner_username)
               VALUES (?, 'default', ?, 'private', ?, ?)""",
            (key_id, _hash_secret(plaintext), int(time.time()), username),
        )
    return plaintext


def create_user(db_path: Path, username: str, password: str) -> tuple[str, str]:
    clean_username = _clean_username(username)
    salt_hex, password_hash = _hash_new_password(password)
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """INSERT INTO users
               (username, password_salt, password_hash, password_iterations, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                clean_username,
                salt_hex,
                password_hash,
                PASSWORD_ITERATIONS,
                int(time.time()),
            ),
        )
    api_key = ensure_default_api_key(db_path, clean_username)
    if api_key is None:
        raise RuntimeError("new user was created without a default API key")
    return clean_username, api_key


def list_users(db_path: Path) -> list[str]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT username FROM users ORDER BY username"
        ).fetchall()
    return [row["username"] for row in rows]


def delete_user(db_path: Path, username: str) -> bool:
    initialize(db_path)
    with _connect(db_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            return False
        now = int(time.time())
        connection.execute("DELETE FROM sessions WHERE username = ?", (username,))
        connection.execute(
            """UPDATE api_keys SET revoked_at = COALESCE(revoked_at, ?),
               owner_username = NULL WHERE owner_username = ?""",
            (now, username),
        )
        connection.execute("DELETE FROM users WHERE username = ?", (username,))
    return True


def update_user_password(db_path: Path, username: str, password: str) -> bool:
    clean_username = _clean_username(username)
    salt_hex, password_hash = _hash_new_password(password)
    initialize(db_path)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            """UPDATE users SET password_salt = ?, password_hash = ?,
               password_iterations = ?, updated_at = ? WHERE username = ?""",
            (
                salt_hex,
                password_hash,
                PASSWORD_ITERATIONS,
                int(time.time()),
                clean_username,
            ),
        )
        if cursor.rowcount:
            connection.execute(
                "DELETE FROM sessions WHERE username = ?", (clean_username,)
            )
    return cursor.rowcount == 1


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


def create_api_key(
    db_path: Path, name: str, kind: str, owner_username: str
) -> tuple[APIKey, str]:
    if kind not in KEY_KINDS:
        raise ValueError("kind must be public or private")
    clean_name = _clean_key_name(name)
    clean_owner = _clean_username(owner_username)
    initialize(db_path)
    key_id = str(uuid.uuid4())
    plaintext = _new_secret(kind)
    with _connect(db_path) as connection:
        owner = connection.execute(
            "SELECT username FROM users WHERE username = ?", (clean_owner,)
        ).fetchone()
        if owner is None:
            raise ValueError(f"user does not exist: {clean_owner}")
        connection.execute(
            """INSERT INTO api_keys
               (id, name, key_hash, kind, created_at, owner_username)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                key_id,
                clean_name,
                _hash_secret(plaintext),
                kind,
                int(time.time()),
                clean_owner,
            ),
        )
    return APIKey(key_id, clean_name, kind, clean_owner), plaintext


def update_api_key(
    db_path: Path,
    key_id: str,
    name: str,
    kind: str,
    owner_username: str | None,
) -> bool:
    if kind not in KEY_KINDS:
        raise ValueError("kind must be public or private")
    clean_name = _clean_key_name(name)
    clean_owner = (
        _clean_username(owner_username) if owner_username is not None else None
    )
    initialize(db_path)
    with _connect(db_path) as connection:
        if clean_owner is not None:
            owner = connection.execute(
                "SELECT username FROM users WHERE username = ?", (clean_owner,)
            ).fetchone()
            if owner is None:
                raise ValueError(f"user does not exist: {clean_owner}")
        cursor = connection.execute(
            """UPDATE api_keys SET name = ?, kind = ?, owner_username = ?
               WHERE id = ? AND revoked_at IS NULL""",
            (clean_name, kind, clean_owner, key_id),
        )
    return cursor.rowcount == 1


def get_api_key(db_path: Path, plaintext: str) -> APIKey | None:
    if not plaintext or len(plaintext) > 256:
        return None
    with _connect(db_path) as connection:
        row = connection.execute(
            """SELECT id, name, kind, owner_username FROM api_keys
               WHERE key_hash = ? AND revoked_at IS NULL""",
            (_hash_secret(plaintext),),
        ).fetchone()
    return (
        APIKey(row["id"], row["name"], row["kind"], row["owner_username"])
        if row
        else None
    )


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
    return (
        APIKey(f"user:{row['username']}", row["username"], "private", row["username"])
        if row
        else None
    )


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
            """SELECT id, name, kind, owner_username, created_at, revoked_at
               FROM api_keys
               ORDER BY created_at, id"""
        ).fetchall()
    return [dict(row) for row in rows]
