import pytest

from tritobol_app.server import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # default export dir (./tritobol_exports) lands in tmp, never in the repo
    return create_app({"TESTING": True})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def hdr(app):
    return {"X-Tritobol-Token": app.config["TRITOBOL_TOKEN"]}


SAMPLE = (
    "Please summarise the quarterly report for the finance team.\n\n"
    "Please summarise the quarterly report for the finance team.\n\n"
    "=========================================\n\n"
    "Revenue grew in Q3.   Costs   were flat.\n"
    "Revenue grew in Q3.\n"
    "Final instruction: list three risks.\n"
)
