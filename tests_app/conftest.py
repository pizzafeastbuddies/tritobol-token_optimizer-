import pytest

from tritobol_app.server import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # default export dir (./tritobol_exports) lands in tmp, never in the repo
    return create_app({
        "TESTING": True,
        "DATABASE_PATH": str(tmp_path / "tritobol.sqlite"),
        "SECRET_KEY": "test-secret-key-not-for-production-use",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def hdr(app, client):
    """Sign in on this client. Optimizer calls require the session cookie plus the page token."""
    token = app.config["TRITOBOL_TOKEN"]
    opened = client.get("/api/auth/session")
    assert opened.status_code == 200
    headers = {"X-Tritobol-Token": token, "X-CSRF-Token": opened.get_json()["csrf_token"]}
    created = client.post("/api/auth/register", json={
        "name": "Workspace User",
        "email": "workspace@example.com",
        "password": "Longerphrase1",
        "confirm": "Longerphrase1",
    }, headers=headers)
    assert created.status_code == 200, created.get_json()
    logged = client.post("/api/auth/login", json={
        "email": "workspace@example.com",
        "password": "Longerphrase1",
    }, headers=headers)
    assert logged.status_code == 200, logged.get_json()
    return {"X-Tritobol-Token": token}


SAMPLE = (
    "Please summarise the quarterly report for the finance team.\n\n"
    "Please summarise the quarterly report for the finance team.\n\n"
    "=========================================\n\n"
    "Revenue grew in Q3.   Costs   were flat.\n"
    "Revenue grew in Q3.\n"
    "Final instruction: list three risks.\n"
)
