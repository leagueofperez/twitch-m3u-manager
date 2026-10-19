import pytest

from app.auth_store import (
    bootstrap_user,
    create_api_key,
    create_session,
    get_api_key,
    get_session,
    revoke_api_key,
    verify_user,
)
from app.config import get_settings


ORIGIN = {"Origin": "http://testserver"}


def test_read_only_key_can_read_but_cannot_mutate(client):
    key, plaintext = create_api_key(
        get_settings().auth_db_path, "reader", "read-only"
    )
    client.post("/api/playlists", json={"name": "visible"})

    assert client.get(
        "/api/playlists", headers={"X-API-Key": plaintext}
    ).status_code == 200
    assert client.post(
        "/api/playlists",
        json={"name": "blocked"},
        headers={"X-API-Key": plaintext},
    ).status_code == 403
    assert key.role == "read-only"
    page = client.get("/", headers={"X-API-Key": plaintext})
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "Crear lista" not in page.text
    playlist = client.get(
        "/p/visible", headers={"X-API-Key": plaintext}
    )
    assert playlist.status_code == 200
    assert playlist.headers["cache-control"] == "no-store"
    assert 'id="add-form"' not in playlist.text
    assert 'data-action="delete-playlist"' not in playlist.text


def test_login_creates_expiring_http_only_session_and_logout_revokes_it(client):
    client.headers.pop("X-API-Key")

    unauthenticated = client.get("/", follow_redirects=False)
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login?next=/"

    page = client.get("/login")
    assert page.status_code == 200
    assert 'id="login-form"' in page.text

    response = client.post(
        "/auth/login",
        json={
            "username": "test-admin",
            "password": "test-password-long-enough",
            "next": "/p/demo",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert response.json()["redirect"] == "/p/demo"
    assert response.cookies["tmm_session"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/").status_code == 200
    session_token = client.cookies["tmm_session"]
    user_session = get_session(get_settings().auth_db_path, session_token)
    assert user_session.name == "test-admin"
    assert user_session.role == "read-write"

    logout = client.post("/auth/logout", json={}, headers=ORIGIN)
    assert logout.status_code == 200
    assert get_session(get_settings().auth_db_path, session_token) is None
    assert client.get("/api/playlists").status_code == 401


def test_login_rejects_bad_passwords_and_external_redirects(client):
    client.headers.pop("X-API-Key")
    bad_password = client.post(
        "/auth/login",
        json={"username": "test-admin", "password": "wrong-password"},
        headers=ORIGIN,
    )
    assert bad_password.status_code == 401

    login = client.post(
        "/auth/login",
        json={
            "username": "test-admin",
            "password": "test-password-long-enough",
            "next": "https://attacker.example/",
        },
        headers=ORIGIN,
    )
    assert login.status_code == 200
    assert login.json()["redirect"] == "/"


def test_login_rejects_cross_origin_requests_and_sets_secure_cookie(client, monkeypatch):
    client.headers.pop("X-API-Key")

    rejected = client.post(
        "/auth/login",
        json={"username": "test-admin", "password": "test-password-long-enough"},
        headers={"Origin": "https://attacker.example"},
    )
    assert rejected.status_code == 403

    monkeypatch.setenv("TWITCH_M3U_COOKIE_SECURE", "true")
    accepted = client.post(
        "/auth/login",
        json={"username": "test-admin", "password": "test-password-long-enough"},
        headers=ORIGIN,
    )
    assert accepted.status_code == 200
    assert "secure" in accepted.headers["set-cookie"].lower()


def test_cookie_authenticated_mutations_require_same_origin(client):
    client.headers.pop("X-API-Key")
    assert client.post(
        "/auth/login",
        json={"username": "test-admin", "password": "test-password-long-enough"},
        headers=ORIGIN,
    ).status_code == 200

    response = client.post("/api/playlists", json={"name": "blocked"})
    assert response.status_code == 403
    assert client.post(
        "/api/playlists",
        json={"name": "allowed"},
        headers=ORIGIN,
    ).status_code == 201


def test_revoking_api_key_invalidates_api_key(client):
    db_path = get_settings().auth_db_path
    key, plaintext = create_api_key(db_path, "revoke", "read-write")

    assert get_api_key(db_path, plaintext) == key
    assert revoke_api_key(db_path, key.id)
    assert get_api_key(db_path, plaintext) is None


def test_expired_sessions_are_rejected(client, monkeypatch):
    import app.auth_store as auth_store

    db_path = get_settings().auth_db_path
    bootstrap_user(db_path, "expires", "expires-password-long-enough")
    now = 1_700_000_000
    monkeypatch.setattr(auth_store.time, "time", lambda: now)
    session_token, expires_at = create_session(db_path, "expires")
    assert expires_at > now

    monkeypatch.setattr(auth_store.time, "time", lambda: expires_at)
    assert get_session(db_path, session_token) is None


def test_startup_bootstraps_and_updates_environment_user(client):
    db_path = get_settings().auth_db_path
    assert verify_user(db_path, "test-admin", "test-password-long-enough")
    assert not verify_user(db_path, "test-admin", "wrong-password")

    bootstrap_user(db_path, "test-admin", "updated-password-long-enough")
    assert verify_user(db_path, "test-admin", "updated-password-long-enough")
    assert not verify_user(db_path, "test-admin", "test-password-long-enough")


def test_startup_replaces_old_configured_username_and_invalidates_sessions(client):
    db_path = get_settings().auth_db_path
    bootstrap_user(db_path, "previous-admin", "previous-password-long-enough")
    session_token, _expires_at = create_session(db_path, "previous-admin")

    bootstrap_user(db_path, "test-admin", "test-password-long-enough")

    assert not verify_user(db_path, "previous-admin", "previous-password-long-enough")
    assert get_session(db_path, session_token) is None


def test_auth_database_migration_keeps_api_keys_but_drops_old_sessions(tmp_path):
    import sqlite3

    from app.auth_store import initialize

    db_path = tmp_path / "legacy-auth.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                revoked_at INTEGER
            );
            CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                api_key_id TEXT NOT NULL REFERENCES api_keys(id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            INSERT INTO api_keys
                (id, name, key_hash, role, created_at)
                VALUES ('key-id', 'existing', 'hash', 'read-only', 1);
            INSERT INTO sessions
                (token_hash, api_key_id, created_at, expires_at)
                VALUES ('session-hash', 'key-id', 1, 9999999999);
            """
        )

    initialize(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sessions)")
        }
        assert "username" in columns
        assert "api_key_id" not in columns
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 1


def test_bootstrap_requires_strong_password(client):
    with pytest.raises(ValueError, match="12 characters"):
        bootstrap_user(get_settings().auth_db_path, "weak-user", "short")


def test_startup_requires_login_credentials(client, monkeypatch):
    import asyncio

    from app.main import app

    monkeypatch.delenv("TWITCH_M3U_LOGIN_USERNAME")
    async def start():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError, match="TWITCH_M3U_LOGIN_USERNAME"):
        asyncio.run(start())


def test_cli_issues_lists_and_revokes_keys_without_persisting_plaintext(
    tmp_path, monkeypatch, capsys
):
    import sqlite3
    import sys

    from app.auth_cli import main

    db_path = tmp_path / "auth.sqlite3"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "auth_cli",
            "--db",
            str(db_path),
            "create",
            "--name",
            "cli-owner",
            "--role",
            "read-write",
        ],
    )
    main()
    created = capsys.readouterr().out
    plaintext = created.split("API key (shown once): ", 1)[1].strip()
    key_id = created.split("Key ID: ", 1)[1].splitlines()[0]

    with sqlite3.connect(db_path) as connection:
        stored_hash = connection.execute(
            "SELECT key_hash FROM api_keys WHERE id = ?", (key_id,)
        ).fetchone()[0]
    assert stored_hash != plaintext
    assert get_api_key(db_path, plaintext) is not None
    assert db_path.stat().st_mode & 0o777 == 0o600

    monkeypatch.setattr(
        sys, "argv", ["auth_cli", "--db", str(db_path), "list"]
    )
    main()
    assert plaintext not in capsys.readouterr().out

    monkeypatch.setattr(
        sys, "argv", ["auth_cli", "--db", str(db_path), "revoke", key_id]
    )
    main()
    assert "Revoked API key" in capsys.readouterr().out
    assert get_api_key(db_path, plaintext) is None
