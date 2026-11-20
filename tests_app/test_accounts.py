"""SQLite accounts: registration, sessions, CSRF, and the workspace gate."""
import sqlite3

from tritobol_app.server import create_app

PASSWORD = "Longerphrase1"
CREATED = "Your account has been created successfully. Please sign in."


def _open(client, app):
    token = app.config["TRITOBOL_TOKEN"]
    session = client.get("/api/auth/session")
    assert session.status_code == 200
    cookie = session.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    return {"X-Tritobol-Token": token, "X-CSRF-Token": session.get_json()["csrf_token"]}


def _register(client, headers, email="ada@example.com", password=PASSWORD, name="Ada Lovelace", confirm=None):
    return client.post("/api/auth/register", json={
        "name": name, "email": email, "password": password, "confirm": PASSWORD if confirm is None else confirm,
    }, headers=headers)


def test_register_login_session_and_logout(client, app):
    headers = _open(client, app)
    created = _register(client, headers)
    assert created.status_code == 200
    assert created.get_json()["message"] == CREATED
    assert client.get("/api/auth/session").get_json()["authenticated"] is False

    logged = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}, headers=headers)
    assert logged.status_code == 200
    body = logged.get_json()
    assert body["user"]["email"] == "ada@example.com"
    assert "password" not in str(body).lower() or "password_hash" not in body
    assert client.get("/api/auth/session").get_json()["authenticated"] is True

    headers = {**headers, "X-CSRF-Token": body["csrf_token"]}
    gone = client.post("/api/auth/logout", json={}, headers=headers)
    assert gone.status_code == 200
    assert client.get("/api/auth/session").get_json()["authenticated"] is False


def test_duplicate_invalid_weak_and_mismatched_registration(client, app):
    headers = _open(client, app)
    assert _register(client, headers).status_code == 200
    again = _register(client, headers)
    assert again.status_code == 409 and again.get_json()["error"]["field"] == "email"
    assert _register(client, headers, email="not-an-email").status_code == 400
    assert _register(client, headers, email="other@example.com", password="short", confirm="short").status_code == 400
    mismatch = _register(client, headers, email="other@example.com", confirm="Differentphrase1")
    assert mismatch.status_code == 400 and mismatch.get_json()["error"]["field"] == "confirm"


def test_wrong_password_and_sql_injection(client, app):
    headers = _open(client, app)
    assert _register(client, headers).status_code == 200
    bad = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "Wrongphrase1"}, headers=headers)
    assert bad.status_code == 401
    injected = client.post("/api/auth/login", json={"email": "' OR 1=1 --", "password": PASSWORD}, headers=headers)
    assert injected.status_code in (400, 401)
    assert client.get("/api/auth/session").get_json()["authenticated"] is False
    with sqlite3.connect(app.config["DATABASE_PATH"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_csrf_required_and_optimizer_requires_session(client, app):
    token = app.config["TRITOBOL_TOKEN"]
    missing = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}, headers={"X-Tritobol-Token": token})
    assert missing.status_code == 403
    blocked = client.post("/api/optimize", json={"text": "hello there"}, headers={"X-Tritobol-Token": token})
    assert blocked.status_code == 401


def test_change_password_keeps_the_session(client, app):
    headers = _open(client, app)
    assert _register(client, headers).status_code == 200
    logged = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}, headers=headers)
    headers = {**headers, "X-CSRF-Token": logged.get_json()["csrf_token"]}
    changed = client.post("/api/auth/password", json={
        "current_password": PASSWORD, "new_password": "Newerphrase1", "confirm": "Newerphrase1",
    }, headers=headers)
    assert changed.status_code == 200
    assert client.get("/api/auth/session").get_json()["authenticated"] is True
    headers = {**headers, "X-CSRF-Token": changed.get_json()["csrf_token"]}
    old = client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}, headers=headers)
    assert old.status_code == 401


def test_database_survives_a_new_process_configuration(tmp_path):
    path = str(tmp_path / "tritobol.sqlite")
    first = create_app({"TESTING": True, "DATABASE_PATH": path, "SECRET_KEY": "a" * 32})
    client = first.test_client()
    headers = _open(client, first)
    assert _register(client, headers, email="kept@example.com").status_code == 200
    second = create_app({"TESTING": True, "DATABASE_PATH": path, "SECRET_KEY": "b" * 32})
    again = second.test_client()
    headers = _open(again, second)
    logged = again.post("/api/auth/login", json={"email": "kept@example.com", "password": PASSWORD}, headers=headers)
    assert logged.status_code == 200
    assert again.get("/api/auth/session").get_json()["user"]["full_name"] == "Ada Lovelace"


def test_database_is_not_served(client, app):
    assert client.get("/data/tritobol.sqlite").status_code == 404
    assert client.get("/static/../data/tritobol.sqlite").status_code in (404, 400)
    with sqlite3.connect(app.config["DATABASE_PATH"]) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
    assert columns == ["id", "full_name", "email", "password_hash", "created_at", "updated_at", "is_active"]
