"""Real-browser end-to-end tests. Skipped automatically if Playwright or a Chromium browser is unavailable.

Run:  pip install playwright && playwright install chromium   (once)
      python -m pytest tests_e2e -q
"""
import hashlib
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")
expect = sync_api.expect
REPO = Path(__file__).resolve().parents[1]
SHOTS = REPO / "docs" / "screenshots"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(cwd: Path):
    port = free_port()
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8", "TRITOBOL_DB": str(cwd / "tritobol.sqlite")}
    proc = subprocess.Popen([sys.executable, "-m", "tritobol_app", "--no-browser", "--port", str(port)],
                            cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "api/health", timeout=1).read()
            return proc, url
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("server did not start: " + proc.stdout.read().decode(errors="replace"))


@pytest.fixture(scope="session")
def workdir(tmp_path_factory):
    return tmp_path_factory.mktemp("e2e_cwd")


@pytest.fixture(scope="session")
def server(workdir):
    proc, url = start_server(workdir)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # no browser binary installed
            pytest.skip(f"Chromium unavailable: {exc}")
        yield b
        b.close()


def _watch(pg, server):
    pg.problems, pg.requests = [], []
    pg.on("console", lambda m: pg.problems.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: pg.problems.append(f"pageerror: {e}"))
    pg.on("request", lambda r: pg.requests.append(r.url))
    pg.server = server


def sign_in(pg, email="workspace@example.com", password="Longerphrase1", name="Workspace User"):
    """Open a real account on this installation. The server itself never auto-signs-in."""
    pg.goto(pg.server + "#/signup")
    pg.wait_for_selector("#signup-email")
    pg.fill("#signup-name", name)
    pg.fill("#signup-email", email)
    pg.fill("#signup-password", password)
    pg.fill("#signup-confirm", password)
    pg.click("#signup-submit")
    pg.wait_for_function(
        """() => location.hash.includes('signin')
            || (document.querySelector('#signup-status')?.textContent || '').toLowerCase().includes('already')"""
    )
    if "signin" not in pg.evaluate("() => location.hash"):
        pg.goto(pg.server + "#/signin")
    pg.wait_for_selector("#signin-password")
    pg.fill("#signin-email", email)
    pg.fill("#signin-password", password)
    pg.click("#signin-submit")
    pg.wait_for_selector("#view-dashboard:not([hidden])")
    pg.wait_for_selector("#dash-engine p")


@pytest.fixture()
def anonymous(browser, server):
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    pg = ctx.new_page()
    _watch(pg, server)
    pg.goto(server)
    pg.wait_for_function("() => document.documentElement.dataset.session === 'out'")
    expect(pg.locator("#view-home")).to_be_visible()
    yield pg
    ctx.close()


@pytest.fixture()
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=server.rstrip("/"))
    pg = ctx.new_page()
    _watch(pg, server)
    pg.goto(server)
    pg.wait_for_function("() => document.documentElement.dataset.session === 'out'")
    sign_in(pg)
    yield pg
    ctx.close()


def shot(pg, name, full=True):
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / f"{name}.png"), full_page=full)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
