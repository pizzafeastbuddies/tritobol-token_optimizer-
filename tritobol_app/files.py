"""Strict, non-destructive decoding of uploaded text files."""

from __future__ import annotations

from pathlib import PurePath

from .schemas import MAX_INPUT_BYTES, AppError

ALLOWED_TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".rst", ".adoc", ".log", ".csv",
    ".json", ".yaml", ".yml", ".py", ".toml", ".ini", ".xml", ".html",
}


def decode_text_upload(filename: str, data: bytes) -> dict:
    """Decode bytes as UTF-8 text or raise a specific AppError. Never alters the source file."""
    name = PurePath((filename or "").replace("\\", "/")).name
    suffix = PurePath(name).suffix.lower()
    if suffix not in ALLOWED_TEXT_SUFFIXES:
        raise AppError(
            "file_error",
            f"Unsupported file type '{suffix or 'none'}'. Allowed: {', '.join(sorted(ALLOWED_TEXT_SUFFIXES))}.",
            field="file",
            status=415,
        )
    if len(data) == 0:
        raise AppError("file_error", "The file is empty.", field="file")
    if len(data) > MAX_INPUT_BYTES:
        raise AppError(
            "input_too_large",
            f"File is {len(data) / 1024 / 1024:.2f} MB; the limit is {MAX_INPUT_BYTES // (1024 * 1024)} MB.",
            field="file",
            status=413,
        )
    if b"\x00" in data:
        raise AppError("file_error", "The file looks binary (contains NUL bytes), not UTF-8 text.", field="file")
    try:
        text = data.decode("utf-8-sig")  # a leading BOM is not content
    except UnicodeDecodeError as exc:
        raise AppError(
            "file_error",
            f"The file is not valid UTF-8 (invalid byte at position {exc.start}). Save it as UTF-8 and retry.",
            field="file",
        ) from exc
    if text.strip() == "":
        raise AppError("file_error", "The file contains only whitespace.", field="file")
    return {"filename": name, "text": text, "bytes": len(data), "chars": len(text)}
