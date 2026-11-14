# Tritobol Application — technical documentation

A local-first web interface for the existing `tritobol` token optimizer. The engine is unchanged in behaviour
(one small crash fix, see [Engine change](#engine-change)); the app adds a JSON API, a browser UI, a diff view,
analytics and safe export.

## Quick start (Windows 10, CMD)

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/> (tick *Add python.exe to PATH*).
2. Extract the project, open CMD in the folder, run:
   ```
   start.bat
   ```
   First run creates `.venv` and installs Flask + tokenizers (internet needed once). Your browser opens at
   `http://127.0.0.1:5000/` (the next free port is used if 5000 is busy; the address is printed).
3. Stop with **Ctrl+C** in the CMD window (or close it).

Manual equivalent:
```
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-app.txt
python -m tritobol_app
```
Options: `python -m tritobol_app --port 8080 --no-browser`.

> **Windows status:** the batch files were written to be Windows-safe (CRLF, `py` launcher fallback, `.venv`), but
> everything in this project was developed and verified on **Linux**. Windows start-up is **not yet verified** —
> see `docs/IMPLEMENTATION_REPORT.md` for the exact commands to verify it.

## Architecture

```
Browser (vanilla ES modules, no build)  --JSON-->  Flask (tritobol_app)  --import-->  tritobol (engine)
```
The engine is the single source of truth: `service.py` calls `Tritobol(...).optimize(text, max_tokens=..., warn_on_truncation=False)`
and shapes the result. No optimization logic exists in Flask or JavaScript.

| Path | Role |
|---|---|
| `tritobol_app/server.py` | app factory, routes, host/origin/token guards, security headers, error handlers |
| `tritobol_app/service.py` | validate → engine → result JSON; tokenizer registry (bundled + uploaded) |
| `tritobol_app/schemas.py` | request validation, `AppError`, limits (2 MB input, 25 MB tokenizer file) |
| `tritobol_app/files.py` | strict UTF-8 decoding of uploaded text files |
| `tritobol_app/diffing.py` | line diff + word-level detail from original vs. actual output, with time/size guard |
| `tritobol_app/export.py` | create-new-only export, filename sanitising |
| `tritobol_app/__main__.py` | `python -m tritobol_app` (loopback-only, port fallback, friendly errors) |
| `static/js/lib.js` | pure helpers (validation, formatting, summaries, diff view-model, history) |
| `static/js/{api,store,editor,results,diffview,analytics,dashboard,settings,app,dom}.js` | UI modules |
| `static/css/tritobol.css` | theme: charcoal, burnt orange, amber; system fonts only |

## API

All responses are JSON. Success: `{"ok": true, ...}`. Failure: `{"ok": false, "error": {"code", "message", "field"}}`.
`POST` requests need header `X-Tritobol-Token` (injected into the page on load).

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness, `local_only`, bundled tokenizer availability, input limit |
| `GET /api/tokenizers` | real tokenizers only: bundled DeepSeek V4.1 Flash + uploaded ones |
| `POST /api/tokenizers/upload` | multipart `file`: a Hugging Face `tokenizer.json` |
| `POST /api/load-file` | multipart `file`: UTF-8 text → `{text, filename, bytes, chars}` |
| `POST /api/optimize` | `{text, tokenizer?, max_tokens?, task_type?, sensitive_data?, protect_code_blocks?}` |
| `POST /api/export` | `{text, filename?, directory?}` → writes a **new** file |

Error codes: `validation_error`, `input_too_large` (413), `file_error`, `tokenizer_error`, `budget_error`,
`processing_error` (500), `export_error`, `forbidden` (403), `not_found`.

`/api/optimize` returns `text`, `stats` (the engine's own numbers: original/optimized tokens and chars, `saved_tokens`,
`saved_percent`, removed counts, `truncated`, `discarded_tokens`), `budget` (requested, and a **re-count** of the output
with `verified_within_budget`), `warning` (the engine's text), `notes`, `segments`, `sensitive_findings` (a count only),
`options`, `diff`, `engine_version`, `elapsed_ms`.

## Tokenizers
Only what exists is offered: the **bundled DeepSeek V4.1 Flash** tokenizer, and any Hugging Face `tokenizer.json`
you upload. Upload is limited to 25 MB, must be valid JSON with a `model` section, must load and pass a sanity
encode/cut check, is kept **in memory only** (max 3, oldest evicted) and the temporary file is deleted in a `finally`.
If the bundled tokenizer cannot load it is shown as *unavailable* with the reason. Counts exclude chat templates and
provider/API overhead — the UI says so.

## Budget and truncation
- Optional, whole number ≥ 1 (validated in the UI and again in the API; `0`, negatives, decimals, `1e3`, text are rejected).
- The engine first applies its cleanup rules; if the result is still over budget, the **newest** tokens are kept and the
  oldest discarded (a token window — truncation, **not** summarising).
- The app re-counts the output and reports whether the budget is really met. Truncation produces a prominent warning with
  the engine's text, the number of discarded tokens and the verification. Text that already fits is reported as such.
- A budget smaller than one character's tokens (e.g. an emoji needs 2 tokens, budget 1) is reported on the budget field
  as "too small" (HTTP 422).

## Diff
Built by `difflib` from the **original input** and the **actual optimizer output** (line level; word-level detail for
paired changed lines), so every removed/kept line is a statement about those two strings. The UI collapses long unchanged
runs and renders in chunks of 400 rows. Because difflib can be pathologically slow on some inputs (measured: 34 s for 2,000
alternating short lines), the matcher has a 5 s cooperative time limit and a 60,000-line cap; when either trips the UI says
"Diff skipped…" and still shows both texts and all statistics.

## Export safety
`export.py` opens files with exclusive creation (`"x"`) only; there is no overwrite path. An existing name gets
`name (1).ext`, `name (2).ext`, …. Names are sanitised (no paths, reserved Windows names, odd characters; allowed extensions
`.txt .md .markdown .rst .json .yaml .yml .py .log`, otherwise `.txt` is appended). Permission, "not a folder" and
disk-full errors become clear messages; a half-written file we created is removed. The browser **Download** button also
creates a new file. Loaded files are read through the browser: the app never receives or writes their path, and tests
prove an original file is byte-identical after load, optimize and export (including exporting under the same name).
Default export folder: `tritobol_exports\` in the folder where the app was started.

## Privacy and security
- Binds to **127.0.0.1** only (not configurable); rejects any `Host` that is not localhost; POSTs need a per-run random
  token and reject cross-site `Origin`. CSP `default-src 'self'`; no CDN, fonts or analytics; **no outbound requests**
  (asserted in browser tests).
- The server stores nothing and logs no request bodies. The browser stores settings and numeric run statistics; original and optimized prompt text is stored only after the user explicitly saves and confirms in Prompt history.
- Saved prompt text remains in versioned local storage for this browser profile and app address only. It is not encrypted by Tritobol and is not synced to other devices. Users can review, restore, copy, delete individual entries, or clear all saved prompt history. The history is capped at 10 entries and 50,000 combined original/result characters per entry.
- Limits: 2 MB input (UTF-8 bytes), 25 MB tokenizer file.
- **Secret detection is pattern-based and incomplete.** It looks for key prefixes of about a dozen providers, `password`/`api_key`-style
  assignments with 12+ character values, PEM private-key blocks and `CONFIDENTIAL:`-style lines. It misses other formats,
  short values, secrets in prose and personal data. In *Leave untouched* mode found values stay in the output (the UI warns when any
  were found); *Replace with [REDACTED]* masks only what was found.
- The built-in server is Flask's development server — adequate for a single local user, not for exposure to a network.

## Engine change
One change to the existing engine, isolated in `docs/engine_patch_tail_indexerror.patch`:
`HuggingFaceTokenizer.tail()` raised `IndexError` when the budget was smaller than the tokens of the newest character
(e.g. emoji with `max_tokens=1`) — also a traceback in the CLI. It now raises `BudgetTooSmallError` (a `ValueError`, which the CLI
already reports cleanly). No other behaviour changed; the 40 original tests pass unmodified. To revert: remove the class and the
`if low > total_tokens - 1:` guard (the app still handles the old `IndexError`).

## Tests
```
python -m pytest tests tests_app -q            # engine + application (needs requirements-dev.txt)
npm install && node --test                     # frontend: unit + UI workflow in jsdom against a real server
pip install playwright && playwright install chromium && python -m pytest tests_e2e -q   # real browser
```
`run_tests.bat` runs the first two on Windows. It always runs **both** suites, prints a summary, and exits **0 only if both pass**; otherwise the exit code is a sum: `1` Python failed, `2` Node failed, `4` Node did not run (Node.js or `node_modules` missing), `8` setup problem (no Python / dependency install failed). Set `TRITOBOL_SKIP_NODE=1` to skip Node deliberately (does not affect the exit code) and `TRITOBOL_NO_PAUSE=1` for automation. Browser tests regenerate `docs/screenshots/`.

## Limits and notes
- Counts are for the supplied text only; no chat template/API overhead.
- Uploaded tokenizers vanish when the app stops.
- Diff may be skipped for very large/pathological inputs (explained in the UI).
- Large inputs take time (≈7 s for 2 MB measured on the development machine); the UI shows progress and a Cancel button
  (cancelling stops waiting; the server finishes the current job).
- Packaging: see "Packaging assessment" in `docs/IMPLEMENTATION_REPORT.md`.
- `pip install .[app]` installs every file under `tritobol_app/static/` (including `favicon.svg`); `tests_app/test_app_packaging.py` fails if a static file is ever left out of `pyproject.toml` package-data.
