---
inclusion: always
---
# Coding standards
- Python >= 3.10, type hints on public functions, `pathlib` for paths, always pass `encoding="utf-8"`.
- Return structured errors via `AppError(code, message, field=None)`; never swallow exceptions into fake success results.
- Never fabricate statistics. Every number shown in the UI must come from the engine or a direct recount.
- Keep dependencies minimal: runtime adds only Flask.
- Windows-safe: no POSIX-only calls; close temp files before reopening them.
