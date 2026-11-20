import hashlib
from pathlib import Path

import pytest

import tritobol_app.export as ex
from tritobol_app.export import export_text, sanitize_filename
from tritobol_app.schemas import AppError


def post(client, hdr, **payload):
    return client.post("/api/export", json=payload, headers=hdr)


def test_export_creates_new_file(client, hdr, tmp_path):
    r = post(client, hdr, text="optimized ✓\n", filename="out.txt", directory=str(tmp_path / "dest"))
    assert r.status_code == 200
    p = Path(r.json["export"]["path"])
    assert p.read_text(encoding="utf-8") == "optimized ✓\n" and p.name == "out.txt" and not r.json["export"]["renamed"]


def test_existing_file_is_never_overwritten(client, hdr, tmp_path):
    existing = tmp_path / "out.txt"
    existing.write_text("PRECIOUS", encoding="utf-8")
    digest = hashlib.sha256(existing.read_bytes()).hexdigest()
    r1 = post(client, hdr, text="new one", filename="out.txt", directory=str(tmp_path))
    r2 = post(client, hdr, text="new two", filename="out.txt", directory=str(tmp_path))
    assert r1.json["export"]["filename"] == "out (1).txt" and r1.json["export"]["renamed"]
    assert r2.json["export"]["filename"] == "out (2).txt"
    assert hashlib.sha256(existing.read_bytes()).hexdigest() == digest
    assert Path(r1.json["export"]["path"]).read_text() == "new one"


def test_original_input_file_unchanged_even_if_export_targets_it(client, hdr, tmp_path):
    original = tmp_path / "prompt.txt"
    original.write_bytes("original  text\r\n\r\n\r\nrepeat repeat".encode())
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    r = post(client, hdr, text="optimized", filename="prompt.txt", directory=str(tmp_path))
    assert r.json["export"]["filename"] == "prompt (1).txt"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest


def test_default_directory_is_created(client, hdr, tmp_path):
    r = post(client, hdr, text="x")
    assert r.status_code == 200 and Path(r.json["export"]["path"]).parent == (tmp_path / "tritobol_exports").resolve()


@pytest.mark.parametrize("raw,expected", [
    ("../../evil.txt", "evil.txt"), ("..\\..\\evil.md", "evil.md"), ("a/b/c.txt", "c.txt"),
    ("", "optimized.txt"), (None, "optimized.txt"), ("report", "report.txt"), ("run.exe", "run.exe.txt"),
    ("CON.txt", "_CON.txt"), ('we<ir>d:na"me?.txt', "we_ir_d_na_me_.txt"), ("..", "optimized.txt"), ("résumé 🎃.md", "résumé 🎃.md"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_empty_text_rejected(client, hdr):
    r = post(client, hdr, text="")
    assert r.status_code == 400 and r.json["error"]["code"] == "export_error"


def test_non_string_text_rejected(client, hdr):
    assert post(client, hdr, text=5).status_code == 400


def test_directory_is_a_file(client, hdr, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    r = post(client, hdr, text="x", directory=str(f))
    assert r.status_code == 400 and r.json["error"]["code"] == "export_error"


def test_permission_error_on_write(tmp_path, monkeypatch):
    real_open = Path.open

    def deny(self, mode="r", *a, **k):
        if "x" in mode:
            raise PermissionError(13, "Permission denied")
        return real_open(self, mode, *a, **k)
    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(AppError) as exc:
        export_text("hi", "a.txt", str(tmp_path))
    assert "Permission denied" in exc.value.message and exc.value.code == "export_error"


def test_permission_error_creating_folder(tmp_path, monkeypatch):
    def deny(self, *a, **k):
        raise PermissionError(13, "denied")
    monkeypatch.setattr(Path, "mkdir", deny)
    with pytest.raises(AppError) as exc:
        export_text("hi", "a.txt", str(tmp_path / "new"))
    assert "Permission denied" in exc.value.message


def test_disk_full_removes_partial_file_and_reports(tmp_path, monkeypatch):
    class Failing:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def write(self, _): raise OSError(28, "No space left on device")
    real_open = Path.open

    def fake(self, mode="r", *a, **k):
        if "x" in mode:
            real_open(self, mode, *a, **k).close()  # really create the file, then fail writing
            return Failing()
        return real_open(self, mode, *a, **k)
    monkeypatch.setattr(Path, "open", fake)
    with pytest.raises(AppError) as exc:
        export_text("hi", "a.txt", str(tmp_path))
    assert "No space left" in exc.value.message and not (tmp_path / "a.txt").exists()


def test_export_never_uses_overwriting_mode():
    import inspect
    src = inspect.getsource(ex)
    assert '"x"' in src and '"w"' not in src and "write_text" not in src


def test_export_requires_token(client):
    assert client.post("/api/export", json={"text": "x"}).status_code == 403
