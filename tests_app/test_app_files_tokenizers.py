import hashlib
import io
import json
import tempfile
from pathlib import Path

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

import tritobol_app.service as svc
from tritobol import HuggingFaceTokenizer
from tritobol_app.schemas import MAX_INPUT_BYTES


def upload(client, hdr, url, name, data):
    return client.post(url, data={"file": (io.BytesIO(data), name)}, headers=hdr, content_type="multipart/form-data")


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------ text files
def test_load_utf8_file_keeps_content(client, hdr, tmp_path):
    src = tmp_path / "notes.txt"
    text = "Héllo 🎃\r\nsecond line\n\n日本語"
    src.write_bytes(text.encode("utf-8"))
    before = md5(src)
    r = upload(client, hdr, "/api/load-file", "notes.txt", src.read_bytes())
    assert r.status_code == 200 and r.json["text"] == text and r.json["filename"] == "notes.txt"
    assert md5(src) == before  # original file untouched


def test_load_strips_bom_only(client, hdr):
    r = upload(client, hdr, "/api/load-file", "a.md", b"\xef\xbb\xbfHello")
    assert r.json["text"] == "Hello"


@pytest.mark.parametrize("name,data,status,fragment", [
    ("e.txt", b"", 400, "empty"),
    ("w.txt", b"  \n\t ", 400, "whitespace"),
    ("bad.txt", "café".encode("latin-1"), 400, "not valid UTF-8"),
    ("bin.txt", b"abc\x00def", 400, "binary"),
    ("pic.png", b"\x89PNG", 415, "Unsupported"),
    ("noext", b"hello", 415, "Unsupported"),
    ("big.txt", b"a" * (MAX_INPUT_BYTES + 1), 413, "limit"),
])
def test_load_errors(client, hdr, name, data, status, fragment):
    r = upload(client, hdr, "/api/load-file", name, data)
    assert r.status_code == status and fragment in r.json["error"]["message"] and r.json["ok"] is False


def test_load_without_file_field(client, hdr):
    r = client.post("/api/load-file", data={}, headers=hdr, content_type="multipart/form-data")
    assert r.status_code == 400 and r.json["error"]["field"] == "file"


def test_load_at_exact_limit_ok(client, hdr):
    assert upload(client, hdr, "/api/load-file", "a.txt", b"a" * MAX_INPUT_BYTES).status_code == 200


# ------------------------------------------------------------- custom tokenizers
def tiny_tokenizer_bytes(words=("hello", "world", "foo", "bar")) -> bytes:
    vocab = {"[UNK]": 0, **{w: i + 1 for i, w in enumerate(words)}}
    tok = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.json"
        tok.save(str(p))
        return p.read_bytes()


def leftover_tmp():
    return list(Path(tempfile.gettempdir()).glob("tritobol_tok_*"))


def test_upload_valid_tokenizer_and_use_it(client, hdr):
    before = len(leftover_tmp())
    r = upload(client, hdr, "/api/tokenizers/upload", "my-tok.json", tiny_tokenizer_bytes())
    assert r.status_code == 200, r.json
    entry = r.json["tokenizer"]
    assert entry["kind"] == "custom" and entry["label"] == "my-tok (uploaded)" and entry["vocab_size"] == 5
    assert len(leftover_tmp()) == before  # temp file removed
    assert [t["id"] for t in client.get("/api/tokenizers").json["tokenizers"]][-1] == entry["id"]
    res = client.post("/api/optimize", json={"text": "hello world foo bar hello", "tokenizer": entry["id"]}, headers=hdr)
    assert res.status_code == 200
    stats = res.json["result"]["stats"]
    assert stats["original_tokens"] == 5 and res.json["result"]["tokenizer"]["id"] == entry["id"]


@pytest.mark.parametrize("name,data,fragment", [
    ("t.txt", b"{}", ".json"),
    ("t.json", b"", "empty"),
    ("t.json", b"not json", "not valid"),
    ("t.json", b"[1,2]", "Hugging Face"),
    ("t.json", b'{"model": 5}', "Hugging Face"),
    ("t.json", b'{"model": {"type": "WordLevel"}}', "could not be loaded"),
    ("t.json", b"\xff\xfe\x00", "not valid"),
])
def test_upload_invalid_tokenizer_rejected_and_cleaned(client, hdr, name, data, fragment):
    before = len(leftover_tmp())
    r = upload(client, hdr, "/api/tokenizers/upload", name, data)
    assert r.status_code in (400, 415) and r.json["error"]["code"] == "tokenizer_error" and fragment in r.json["error"]["message"]
    assert len(leftover_tmp()) == before
    assert len(client.get("/api/tokenizers").json["tokenizers"]) == 1


def test_upload_size_limit(client, hdr, monkeypatch):
    monkeypatch.setattr(svc, "MAX_TOKENIZER_BYTES", 100)
    r = upload(client, hdr, "/api/tokenizers/upload", "t.json", tiny_tokenizer_bytes())
    assert r.status_code == 413 and "limit" in r.json["error"]["message"]


def test_custom_tokenizer_cap_evicts_oldest(client, hdr):
    ids = [upload(client, hdr, "/api/tokenizers/upload", f"t{i}.json", tiny_tokenizer_bytes()).json["tokenizer"]["id"] for i in range(5)]
    listed = [t["id"] for t in client.get("/api/tokenizers").json["tokenizers"] if t["kind"] == "custom"]
    assert listed == ids[-3:]


def test_tokenizer_failing_sanity_check_is_rejected(client, hdr, monkeypatch):
    def broken_init(self, path, model_name=None):
        raise RuntimeError("bad vocab")
    monkeypatch.setattr(HuggingFaceTokenizer, "__init__", broken_init)
    monkeypatch.setattr(svc, "HuggingFaceTokenizer", HuggingFaceTokenizer)
    before = len(leftover_tmp())
    r = upload(client, hdr, "/api/tokenizers/upload", "t.json", tiny_tokenizer_bytes())
    assert r.status_code == 400 and "bad vocab" in r.json["error"]["message"] and len(leftover_tmp()) == before


def test_upload_requires_token(client):
    r = client.post("/api/tokenizers/upload", data={"file": (io.BytesIO(b"{}"), "t.json")}, content_type="multipart/form-data")
    assert r.status_code == 403
