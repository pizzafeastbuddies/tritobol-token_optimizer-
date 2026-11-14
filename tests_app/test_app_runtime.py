"""Process-level tests: real server start/stop, loopback binding, startup errors, secret scan, CLI/API consistency."""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import SAMPLE
from tritobol import Tritobol

REPO = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launch(port, cwd):
    proc = subprocess.Popen([sys.executable, "-m", "tritobol_app", "--no-browser", "--port", str(port)], cwd=cwd, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).read()
            return proc
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("did not start")


def test_real_server_starts_serves_assets_and_stops(tmp_path):
    port = free_port()
    proc = launch(port, tmp_path)
    try:
        base = f"http://127.0.0.1:{port}"
        assert json.load(urllib.request.urlopen(base + "/api/health"))["local_only"] is True
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "tritobol-token" in html and "__TRITOBOL_TOKEN__" not in html
        for path in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
            assert urllib.request.urlopen(base + path).status == 200, path
        for mod in ("app", "api", "lib", "store", "editor", "results", "diffview", "analytics", "dashboard", "settings", "dom"):
            assert urllib.request.urlopen(f"{base}/static/js/{mod}.js").status == 200
    finally:
        proc.terminate()
        out = proc.communicate(timeout=10)[0].decode(errors="replace")
    assert "Tritobol is running at http://127.0.0.1:" in out and "Traceback" not in out
    with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):  # really stopped
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)


def test_server_listens_on_loopback_only(tmp_path):
    port = free_port()
    proc = launch(port, tmp_path)
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1", "127.0.1.1"}
        if not ips:
            pytest.skip("no non-loopback interface to probe")
        for ip in ips:
            with socket.socket() as s:
                s.settimeout(2)
                assert s.connect_ex((ip, port)) != 0, f"server reachable on {ip}"
    finally:
        proc.terminate()
        proc.communicate(timeout=10)


def test_port_in_use_falls_back_to_next_port(tmp_path):
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        proc = subprocess.Popen([sys.executable, "-m", "tritobol_app", "--no-browser", "--port", str(busy)], cwd=tmp_path, env=ENV,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            time.sleep(3)
            line = b""
            os.set_blocking(proc.stdout.fileno(), False)
            try:
                line = proc.stdout.read() or b""
            except Exception:
                pass
            assert f":{busy}/".encode() not in line and b"running at http://127.0.0.1:" in line
        finally:
            proc.terminate()
            proc.communicate(timeout=10)


def test_missing_flask_gives_actionable_message():
    code = "import sys; sys.modules['flask']=None; from tritobol_app.__main__ import main; sys.exit(main(['--no-browser']))"
    p = subprocess.run([sys.executable, "-c", code], env=ENV, capture_output=True, text=True)
    assert p.returncode == 1 and "missing dependency" in p.stderr and "pip install -r requirements-app.txt" in p.stderr
    assert "Traceback" not in p.stderr


def test_no_secrets_or_external_urls_in_application_source():
    patterns = [r"sk-[A-Za-z0-9]{16,}", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY", r"(?i)(password|api_key|secret)\s*[:=]\s*['\"][^'\"]{8,}"]
    for f in (REPO / "tritobol_app").rglob("*"):
        if f.suffix in (".py", ".js", ".html", ".css", ".svg") and f.is_file():
            text = f.read_text(encoding="utf-8")
            for pat in patterns:
                assert not re.search(pat, text), f"{f.name} matches {pat}"
            urls = [u for u in re.findall(r"https?://[^\s\"'<>)]+", text) if "w3.org" not in u and "127.0.0.1" not in u and "{HOST}" not in u]
            assert urls == [], f"{f.name} references external URLs: {urls}"


def test_service_delegates_to_the_real_engine(client, hdr, monkeypatch):
    import tritobol_app.service as svc
    calls = []
    real = svc.Tritobol.optimize

    def spy(self, text, **kwargs):
        calls.append((text, kwargs))
        return real(self, text, **kwargs)
    monkeypatch.setattr(svc.Tritobol, "optimize", spy)
    r = client.post("/api/optimize", json={"text": SAMPLE, "max_tokens": 30}, headers=hdr)
    assert r.status_code == 200 and len(calls) == 1
    assert calls[0][0] == SAMPLE and calls[0][1] == {"max_tokens": 30, "warn_on_truncation": False}


def test_cli_and_api_agree_on_the_same_input(client, hdr, tmp_path):
    src = tmp_path / "in.txt"
    src.write_text(SAMPLE, encoding="utf-8")
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    cli = subprocess.run([sys.executable, "-m", "tritobol", str(src)], capture_output=True, text=True, encoding="utf-8", env=ENV)
    api = client.post("/api/optimize", json={"text": SAMPLE}, headers=hdr).json["result"]
    assert cli.returncode == 0 and cli.stdout.rstrip("\n") == api["text"].rstrip("\n")
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before  # CLI and API never modify the source


def test_complete_user_journey_via_api(client, hdr, tmp_path):
    """Open -> load file -> tokenizer -> budget -> optimize -> compare/diff -> export -> original unchanged."""
    original = tmp_path / "source.txt"
    original.write_bytes(SAMPLE.encode("utf-8"))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert client.get("/").status_code == 200
    toks = client.get("/api/tokenizers").json["tokenizers"]
    loaded = client.post("/api/load-file", data={"file": (original.open("rb"), "source.txt")}, headers=hdr, content_type="multipart/form-data").json
    assert loaded["text"] == SAMPLE
    res = client.post("/api/optimize", json={"text": loaded["text"], "tokenizer": toks[0]["id"], "max_tokens": 25}, headers=hdr).json["result"]
    direct = Tritobol().optimize(SAMPLE, max_tokens=25, warn_on_truncation=False)
    assert res["text"] == direct.text and res["stats"]["optimized_tokens"] == direct.stats.optimized_tokens
    assert res["diff"]["available"] and res["budget"]["verified_within_budget"] is True
    out = tmp_path / "exports"
    exp = client.post("/api/export", json={"text": res["text"], "filename": "source.txt", "directory": str(out)}, headers=hdr).json["export"]
    assert Path(exp["path"]).read_text(encoding="utf-8") == res["text"]
    exp2 = client.post("/api/export", json={"text": res["text"], "filename": "source.txt", "directory": str(tmp_path)}, headers=hdr).json["export"]
    assert exp2["filename"] == "source (1).txt" and exp2["renamed"]  # same name as the original: never overwritten
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest


def test_input_at_exact_2mb_limit_is_processed(client, hdr):
    text = "".join(f"Paragraph {i}: unique content about topic {i % 977} with words.\n\n" for i in range(40000))
    text = text[: 2 * 1024 * 1024]
    assert len(text.encode("utf-8")) == 2 * 1024 * 1024
    t = time.perf_counter()
    r = client.post("/api/optimize", json={"text": text}, headers=hdr)
    assert r.status_code == 200 and time.perf_counter() - t < 90
    body = r.json["result"]
    assert body["stats"]["original_chars"] == len(text) and body["diff"]["available"] in (True, False)
    if not body["diff"]["available"]:
        assert "skipped" in body["diff"]["reason"] and body["text"]  # explained, never silently missing
