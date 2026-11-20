import json

import pytest

from conftest import SAMPLE
from tritobol import Tritobol
from tritobol.tokenizer import get_default_tokenizer


def post(client, hdr, payload, **kw):
    return client.post("/api/optimize", json=payload, headers=hdr, **kw)


def test_health_and_tokenizers(client):
    assert client.get("/api/health").json["ok"] is True
    toks = client.get("/api/tokenizers").json["tokenizers"]
    assert [t["id"] for t in toks] == ["deepseek-v4.1-flash"]  # only what really exists
    assert toks[0]["available"] and toks[0]["vocab_size"] == 129280


def test_result_matches_engine_exactly(client, hdr):
    """The API must return the engine's own numbers (no duplicated logic)."""
    direct = Tritobol().optimize(SAMPLE, warn_on_truncation=False)
    body = post(client, hdr, {"text": SAMPLE}).json["result"]
    assert body["text"] == direct.text
    s = body["stats"]
    assert (s["original_tokens"], s["optimized_tokens"], s["saved_tokens"]) == (
        direct.stats.original_tokens, direct.stats.optimized_tokens, direct.stats.saved_tokens)
    assert s["saved_percent"] == pytest.approx(direct.stats.saved_percent)
    assert s["saved_tokens"] == s["original_tokens"] - s["optimized_tokens"]
    assert s["original_tokens"] == get_default_tokenizer().count(SAMPLE)
    assert body["warning"] is None and body["budget"]["enforced"] is False
    assert [x["kind"] for x in body["segments"]] == [x.kind for x in direct.segments]


def test_no_savings_reports_zero_not_forced_positive(client, hdr):
    r = post(client, hdr, {"text": "One short unique line."}).json["result"]["stats"]
    assert r["saved_tokens"] == 0 and r["saved_percent"] == 0.0


def test_negative_savings_is_shown_truthfully(client, hdr):
    # mask mode can replace a secret with [REDACTED]; whatever the engine reports must be passed through.
    text = "password = 'abcdefghijkl'"
    direct = Tritobol(sensitive_data="mask").optimize(text, warn_on_truncation=False)
    s = post(client, hdr, {"text": text, "sensitive_data": "mask"}).json["result"]["stats"]
    assert s["saved_tokens"] == direct.stats.saved_tokens
    assert s["saved_percent"] == pytest.approx(direct.stats.saved_percent)


def test_unicode_emoji_multiline(client, hdr):
    text = "Héllo wörld 🎃🎃\n\n日本語のテキストです。これは長い文です。\n\nline\u200bwith zero-width"
    r = post(client, hdr, {"text": text}).json["result"]
    assert "🎃" in r["text"] and "日本語" in r["text"] and "\u200b" not in r["text"]


def test_truncation_warning_budget_below_input(client, hdr, capsys):
    text = " ".join(f"word{i}" for i in range(400))
    r = post(client, hdr, {"text": text, "max_tokens": 20}).json["result"]
    assert r["stats"]["truncated"] and r["stats"]["discarded_tokens"] > 0
    assert "truncated" in r["warning"] and "max_tokens=20" in r["warning"]
    assert r["budget"]["verified_within_budget"] is True and r["budget"]["recount_tokens"] <= 20
    assert r["text"].endswith("word399")  # newest content kept
    assert capsys.readouterr().err == ""  # warning is returned in JSON, not printed


@pytest.mark.parametrize("budget", [1, 2])
def test_very_small_budgets(client, hdr, budget):
    r = post(client, hdr, {"text": "alpha beta gamma delta epsilon", "max_tokens": budget}).json["result"]
    assert r["budget"]["recount_tokens"] <= budget and r["stats"]["truncated"]


def test_budget_equal_to_input_tokens_not_truncated(client, hdr):
    text = "alpha beta gamma delta"
    n = Tritobol().count_tokens(text)
    r = post(client, hdr, {"text": text, "max_tokens": n}).json["result"]
    assert r["stats"]["truncated"] is False and r["warning"] is None and r["text"] == text


def test_large_budget_notes_no_cut(client, hdr):
    r = post(client, hdr, {"text": "short text here", "max_tokens": 10_000_000}).json["result"]
    assert not r["stats"]["truncated"] and any("already fit" in n for n in r["notes"])


@pytest.mark.parametrize("budget", [0, -4, "x", 2.5, True])
def test_bad_budget_rejected(client, hdr, budget):
    resp = post(client, hdr, {"text": "hello world", "max_tokens": budget})
    assert resp.status_code == 400 and resp.json["error"]["code"] == "budget_error"


@pytest.mark.parametrize("payload,code,status", [
    ({"text": ""}, "validation_error", 400),
    ({"text": "   \n  "}, "validation_error", 400),
    ({"text": "hi", "tokenizer": "nope"}, "tokenizer_error", 400),
    ({"text": "hi", "task_type": "x"}, "validation_error", 400),
])
def test_validation_errors(client, hdr, payload, code, status):
    resp = post(client, hdr, payload)
    assert resp.status_code == status and resp.json["ok"] is False and resp.json["error"]["code"] == code


def test_input_over_2mb_rejected_with_clear_message(client, hdr):
    resp = post(client, hdr, {"text": "a" * (2 * 1024 * 1024 + 1)})
    assert resp.status_code == 413 and "limit is 2 MB" in resp.json["error"]["message"]


def test_non_json_body(client, hdr):
    resp = client.post("/api/optimize", data="not json", headers=hdr, content_type="text/plain")
    assert resp.status_code == 400 and resp.json["error"]["code"] == "validation_error"


def test_unknown_route_json_404(client):
    r = client.get("/api/nothing")
    assert r.status_code == 404 and r.json["error"]["code"] == "not_found"


# ---- guards ---------------------------------------------------------------
def test_post_requires_token(client):
    assert client.post("/api/optimize", json={"text": "x"}).status_code == 403
    assert client.post("/api/optimize", json={"text": "x"}, headers={"X-Tritobol-Token": "wrong"}).status_code == 403


def test_non_local_host_rejected(client, hdr):
    assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "localhost:5000"}).status_code == 200


def test_cross_site_origin_rejected(client, hdr):
    h = {**hdr, "Origin": "https://evil.example.com"}
    assert client.post("/api/optimize", json={"text": "hi there"}, headers=h).status_code == 403
    h = {**hdr, "Origin": "http://127.0.0.1:5000"}
    assert client.post("/api/optimize", json={"text": "hi there"}, headers=h).status_code == 200


def test_index_injects_token_and_security_headers(client, app):
    r = client.get("/")
    assert app.config["TRITOBOL_TOKEN"] in r.get_data(as_text=True) and "__TRITOBOL_TOKEN__" not in r.get_data(as_text=True)
    assert "default-src 'self'" in r.headers["Content-Security-Policy"] and r.headers["Cache-Control"] == "no-store"


# ---- failure paths ---------------------------------------------------------
def test_bundled_tokenizer_unavailable(client, hdr, monkeypatch):
    import tritobol_app.service as svc

    def boom():
        raise OSError("tokenizer file missing")
    monkeypatch.setattr(svc, "get_default_tokenizer", boom)
    toks = client.get("/api/tokenizers").json["tokenizers"]
    assert toks[0]["available"] is False and "tokenizer file missing" in toks[0]["error"]
    r = post(client, hdr, {"text": "hello world"})
    assert r.status_code == 500 and r.json["error"]["code"] == "tokenizer_error"


def test_engine_exception_becomes_structured_error_without_echoing_input(client, hdr, monkeypatch):
    import tritobol_app.service as svc

    class Broken(svc.Tritobol):
        def optimize(self, *a, **k):
            raise RuntimeError("internal SECRET-LEAK-CHECK")
    monkeypatch.setattr(svc, "Tritobol", Broken)
    r = post(client, hdr, {"text": "my private text"})
    assert r.status_code == 500 and r.json["error"]["code"] == "processing_error"
    assert "my private text" not in json.dumps(r.json) and "SECRET-LEAK-CHECK" not in json.dumps(r.json)


def test_sensitive_modes_pass_through_and_never_echo_values(client, hdr):
    text = "Config: api_key = 'sk-abcdefghijklmnop12345' and more text follows here."
    masked = post(client, hdr, {"text": text, "sensitive_data": "mask"}).json["result"]
    assert "sk-abcdefghijklmnop12345" not in masked["text"] and "[REDACTED]" in masked["text"]
    assert masked["sensitive_findings"] >= 1
    assert "sk-abcdefghijklmnop12345" not in json.dumps(masked["segments"])
    kept = post(client, hdr, {"text": text, "sensitive_data": "skip"}).json["result"]
    assert "sk-abcdefghijklmnop12345" in kept["text"]  # skip preserves; UI must say so


@pytest.mark.parametrize("char", ["🎃", "Ń"])
def test_known_engine_limit_budget_smaller_than_one_character(client, hdr, char):
    """Engine bug (IndexError in tail()) is surfaced as a clear 422 instead of a crash or a fake result."""
    r = post(client, hdr, {"text": char, "max_tokens": 1})
    assert r.status_code == 422 and r.json["error"]["code"] == "budget_error" and r.json["error"]["field"] == "max_tokens"
    assert "too small" in r.json["error"]["message"]
    ok = post(client, hdr, {"text": char, "max_tokens": 2})  # a workable budget still succeeds
    assert ok.status_code == 200 and ok.json["result"]["text"] == char
