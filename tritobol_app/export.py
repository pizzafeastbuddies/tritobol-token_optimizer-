"""Create-new-only export of optimized text. Never overwrites an existing file."""

from __future__ import annotations

import re
from pathlib import Path, PurePath
from typing import Optional

from .schemas import AppError

ALLOWED_EXPORT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".json", ".yaml", ".yml", ".py", ".log"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_EXPORT_ATTEMPTS = 1000


def default_export_dir() -> Path:
    return Path.cwd() / "tritobol_exports"


def sanitize_filename(name: Optional[str]) -> str:
    base = PurePath((name or "").replace("\\", "/")).name.strip().strip(".")
    base = _BAD_CHARS.sub("_", base)
    if not base:
        base = "optimized.txt"
    stem, dot, suffix = base.rpartition(".")
    if not dot:
        stem, suffix = base, ""
    else:
        suffix = "." + suffix.lower()
    if suffix not in ALLOWED_EXPORT_SUFFIXES:
        stem, suffix = base, ".txt"
    if stem.upper().split(".")[0] in _RESERVED:
        stem = "_" + stem
    return (stem[:120] or "optimized") + suffix


def export_text(text: str, filename: Optional[str] = None, directory: Optional[str] = None) -> dict:
    """Write text to a brand-new file. Uses exclusive creation so existing files are never touched."""
    if not isinstance(text, str):
        raise AppError("validation_error", "'text' must be a string.", field="text")
    if text == "":
        raise AppError("export_error", "There is no optimized text to export.", field="text")
    safe_name = sanitize_filename(filename)
    if directory is not None and not isinstance(directory, str):
        raise AppError("validation_error", "'directory' must be a string.", field="directory")
    target_dir = Path(directory).expanduser() if directory and directory.strip() else default_export_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise AppError("export_error", f"Permission denied creating the folder: {target_dir}", field="directory") from exc
    except OSError as exc:
        raise AppError("export_error", f"Could not use folder '{target_dir}': {exc.strerror or exc}", field="directory") from exc
    if not target_dir.is_dir():
        raise AppError("export_error", f"Destination is not a folder: {target_dir}", field="directory")

    stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
    for attempt in range(MAX_EXPORT_ATTEMPTS):
        candidate = target_dir / (safe_name if attempt == 0 else f"{stem} ({attempt}){suffix}")
        try:
            stream = candidate.open("x", encoding="utf-8", newline="")  # exclusive create: fails if it exists
        except FileExistsError:
            continue
        except PermissionError as exc:
            raise AppError("export_error", f"Permission denied writing to: {target_dir}", field="directory") from exc
        except OSError as exc:
            raise AppError("export_error", f"Could not create the file: {exc.strerror or exc}") from exc
        try:
            with stream:
                stream.write(text)
        except OSError as exc:
            _cleanup_partial(candidate)  # we created this file a moment ago, so removing it is safe
            raise AppError("export_error", f"Could not write the file (disk full or I/O error): {exc.strerror or exc}") from exc
        return {
            "path": str(candidate.resolve()),
            "filename": candidate.name,
            "renamed": attempt > 0,
            "bytes": len(text.encode("utf-8")),
        }
    raise AppError("export_error", "Too many files with that name already exist; choose another name.", field="filename")


def _cleanup_partial(path: Path) -> None:
    """Remove a file we just created if the write failed (e.g. disk full). Only called after exclusive create."""
    try:
        path.unlink()
    except OSError:
        pass
