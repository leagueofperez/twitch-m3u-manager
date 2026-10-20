import pytest

from app.auth_store import (
    bootstrap_user,
    create_api_key,
    create_session,
    create_user,
    delete_user,
    get_api_key,
    get_session,
    list_api_keys,
    list_users,
    revoke_api_key,
    update_api_key,
    update_user_password,
    verify_user,
)
from app.config import get_settings


ORIGIN = {"Origin": "http://testserver"}


def test_read_only_key_can_read_but_cannot_mutate(client):
    key, plaintext = create_api_key(
        get_settings().auth_db_path, "reader", "read-only", "test-admin"
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
    assert 'method="post"' in page.text
    assert 'action="/auth/login"' in page.text

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


def test_login_form_posts_credentials_in_body_and_redirects_without_query(client):
    client.headers.pop("X-API-Key")
    page = client.get("/login?next=%2Fp%2Fdemo")
    assert page.status_code == 200
    assert "name=\"next\" value=\"/p/demo\"" in page.text

    response = client.post(
        "/auth/login",
        data={
            "username": "test-admin",
            "password": "test-password-long-enough",
            "next": "/p/demo",
        },
        headers=ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert str(response.request.url) == "http://testserver/auth/login"
    assert response.headers["location"] == "/p/demo"
    assert response.cookies["tmm_session"]
    assert "secure" not in response.headers["set-cookie"].lower()


def test_login_endpoint_rejects_get_instead_of_putting_credentials_in_url(client):
    response = client.get(
        "/auth/login",
        params={
            "username": "test-admin",
            "password": "test-password-long-enough",
        },
    )
    assert response.status_code == 405


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
    key, plaintext = create_api_key(db_path, "revoke", "read-write", "test-admin")

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
    initial_key = bootstrap_user(
        db_path, "test-admin", "test-password-long-enough"
    )
    assert initial_key is None
    keys = list_api_keys(db_path)
    default_key = next(key for key in keys if key["name"] == "default")
    assert default_key["owner_username"] == "test-admin"
    assert default_key["role"] == "read-write"

    replacement = bootstrap_user(
        db_path, "test-admin", "updated-password-long-enough"
    )
    assert replacement is None
    assert verify_user(db_path, "test-admin", "updated-password-long-enough")
    assert not verify_user(db_path, "test-admin", "test-password-long-enough")


def test_startup_bootstrap_preserves_additional_users_and_sessions(client):
    db_path = get_settings().auth_db_path
    bootstrap_user(db_path, "previous-admin", "previous-password-long-enough")
    session_token, _expires_at = create_session(db_path, "previous-admin")

    bootstrap_user(db_path, "test-admin", "test-password-long-enough")

    assert verify_user(db_path, "previous-admin", "previous-password-long-enough")
    assert get_session(db_path, session_token).name == "previous-admin"


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
    bootstrap_user(db_path, "migration-admin", "migration-password-long-enough")

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sessions)")
        }
        assert "username" in columns
        assert "api_key_id" not in columns
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 2
        owner = connection.execute(
            "SELECT owner_username FROM api_keys WHERE id = 'key-id'"
        ).fetchone()[0]
        assert owner == "migration-admin"
        generated_key = connection.execute(
            """SELECT name, role, owner_username FROM api_keys
               WHERE id != 'key-id'"""
        ).fetchone()
        assert tuple(generated_key) == ("default", "read-write", "migration-admin")


def test_bootstrap_requires_strong_password(client):
    with pytest.raises(ValueError, match="12 characters"):
        bootstrap_user(get_settings().auth_db_path, "weak-user", "short")


def test_bootstrap_generates_one_default_key_for_new_configured_user(tmp_path):
    from app.auth_store import get_api_key

    db_path = tmp_path / "auth.sqlite3"
    generated_key = bootstrap_user(
        db_path, "first-admin", "first-admin-password-long-enough"
    )

    assert generated_key is not None
    stored_key = get_api_key(db_path, generated_key)
    assert stored_key.name == "default"
    assert stored_key.owner_username == "first-admin"
    assert stored_key.role == "read-write"
    assert (
        bootstrap_user(db_path, "first-admin", "first-admin-password-long-enough")
        is None
    )
    assert sum(key["name"] == "default" for key in list_api_keys(db_path)) == 1


def test_password_update_changes_credentials_and_revokes_sessions(tmp_path):
    db_path = tmp_path / "auth.sqlite3"
    create_user(db_path, "password-user", "original-password-long-enough")
    session_token, _expires_at = create_session(db_path, "password-user")

    assert update_user_password(
        db_path, "password-user", "replacement-password-long-enough"
    )
    assert verify_user(db_path, "password-user", "replacement-password-long-enough")
    assert not verify_user(db_path, "password-user", "original-password-long-enough")
    assert get_session(db_path, session_token) is None
    assert not update_user_password(
        db_path, "missing-user", "replacement-password-long-enough"
    )


def test_api_key_metadata_update_validates_owner_and_preserves_secret(tmp_path):
    db_path = tmp_path / "auth.sqlite3"
    create_user(db_path, "first-owner", "first-owner-password-long-enough")
    create_user(db_path, "second-owner", "second-owner-password-long-enough")
    key, plaintext = create_api_key(
        db_path, "original", "read-only", "first-owner"
    )

    assert update_api_key(
        db_path, key.id, "renamed", "read-write", "second-owner"
    )
    updated = get_api_key(db_path, plaintext)
    assert updated.id == key.id
    assert updated.name == "renamed"
    assert updated.role == "read-write"
    assert updated.owner_username == "second-owner"
    with pytest.raises(ValueError, match="user does not exist"):
        update_api_key(db_path, key.id, "renamed", "read-write", "missing-user")
    assert not update_api_key(
        db_path, "missing-key", "renamed", "read-write", "second-owner"
    )


def test_startup_requires_login_credentials(client, monkeypatch):
    import asyncio

    from app.main import app

    monkeypatch.delenv("TWITCH_M3U_LOGIN_USERNAME")
    async def start():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError, match="TWITCH_M3U_LOGIN_USERNAME"):
        asyncio.run(start())


def test_interactive_cli_manages_users_and_api_keys(
    tmp_path, monkeypatch, capsys
):
    import sqlite3
    import sys

    import app.auth_cli as auth_cli

    db_path = tmp_path / "auth.sqlite3"
    create_user(db_path, "cli-owner", "cli-owner-password-long-enough")
    editable_key, old_plaintext = create_api_key(
        db_path, "before", "read-only", "cli-owner"
    )
    created_password = "new-user-password-long-enough"
    updated_password = "replacement-password-long-enough"
    plaintexts = iter(
        [
            created_password,
            created_password,
            updated_password,
            updated_password,
        ]
    )
    responses = iter(
        [
            "",  # Keep the configured database.
            "1", "2", "api-user",  # Create a user.
            "0",  # Return to the main menu.
            "2", "2", "created-key", "read-only", "api-user",  # Create key.
            "1",  # List keys; secrets must not appear.
            "3", editable_key.id, "renamed", "read-write", "api-user",
            "4", editable_key.id, "y",  # Revoke edited key.
            "0",  # Return to main menu.
            "1", "3", "api-user",  # Change user password.
            "4", "cli-owner", "y",  # Delete another user.
            "0",  # Return to main menu.
            "0",  # Exit.
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    monkeypatch.setattr(auth_cli.getpass, "getpass", lambda _prompt: next(plaintexts))
    monkeypatch.setattr(sys, "argv", ["auth_cli"])
    monkeypatch.setenv("TWITCH_M3U_AUTH_DB", str(db_path))

    auth_cli.main()
    output = capsys.readouterr().out

    assert output.count("Default read-write API key (shown once):") == 1
    assert output.count("\nAPI key (shown once):") == 1
    assert old_plaintext not in output
    default_secret = output.split(
        "Default read-write API key (shown once): ", 1
    )[1].splitlines()[0]
    created_secret = output.split("\nAPI key (shown once): ", 1)[1].splitlines()[0]
    assert output.count(default_secret) == 1
    assert output.count(created_secret) == 1
    default_key = get_api_key(db_path, default_secret)
    assert default_key.name == "default"
    assert default_key.owner_username == "api-user"
    created_key_secret = get_api_key(db_path, created_secret)
    assert created_key_secret.name == "created-key"
    assert created_key_secret.owner_username == "api-user"
    with sqlite3.connect(db_path) as connection:
        stored_hash = connection.execute(
            "SELECT key_hash FROM api_keys WHERE id = ?",
            (created_key_secret.id,),
        ).fetchone()[0]
    assert stored_hash != created_secret
    assert "api-user" in list_users(db_path)
    assert verify_user(db_path, "api-user", updated_password)
    assert not verify_user(db_path, "api-user", created_password)
    assert "cli-owner" not in list_users(db_path)
    created_key = next(
        key for key in list_api_keys(db_path) if key["name"] == "created-key"
    )
    assert created_key["owner_username"] == "api-user"
    assert created_key["revoked_at"] is None
    edited_key = next(
        key for key in list_api_keys(db_path) if key["id"] == editable_key.id
    )
    assert edited_key["name"] == "renamed"
    assert edited_key["role"] == "read-write"
    assert edited_key["owner_username"] == "api-user"
    assert edited_key["revoked_at"] is not None
    assert get_api_key(db_path, old_plaintext) is None


def test_interactive_cli_can_select_an_alternate_database(
    tmp_path, monkeypatch, capsys
):
    import sys

    import app.auth_cli as auth_cli

    configured_db = tmp_path / "configured.sqlite3"
    alternate_db = tmp_path / "alternate.sqlite3"
    monkeypatch.setenv("TWITCH_M3U_AUTH_DB", str(configured_db))
    responses = iter([str(alternate_db), "0"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    monkeypatch.setattr(sys, "argv", ["auth_cli"])

    auth_cli.main()

    assert configured_db.exists()
    assert alternate_db.exists()
    assert alternate_db.stat().st_mode & 0o777 == 0o600
    assert str(alternate_db) in capsys.readouterr().out


def test_interactive_cli_rejects_command_line_arguments(monkeypatch, capsys):
    import sys

    from app.auth_cli import main

    monkeypatch.setattr(sys, "argv", ["auth_cli", "users", "list"])
    main()
    assert "does not accept command-line arguments" in capsys.readouterr().out


def test_startup_does_not_reassign_deleted_users_keys(client):
    db_path = get_settings().auth_db_path
    create_user(db_path, "removed-user", "removed-user-password-long-enough")
    user_key, plaintext = create_api_key(
        db_path, "custom", "read-only", "removed-user"
    )

    assert delete_user(db_path, "removed-user")
    bootstrap_user(db_path, "test-admin", "test-password-long-enough")

    stored = next(key for key in list_api_keys(db_path) if key["id"] == user_key.id)
    assert stored["revoked_at"] is not None
    assert stored["owner_username"] is None
    assert get_api_key(db_path, plaintext) is None
