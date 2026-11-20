# Design — Tritobol Application

```
Browser (vanilla ES modules, no build)  --JSON-->  Flask (tritobol_app)  --import-->  tritobol (unchanged)
```

## Modules
| Module | Responsibility |
|---|---|
| `tritobol_app/server.py` | Flask app factory, routes, host/token guards, error handlers |
| `tritobol_app/service.py` | validate -> engine call -> result dict; tokenizer registry |
| `tritobol_app/schemas.py` | request validation, `AppError`, error codes |
| `tritobol_app/diffing.py` | diff from original vs actual output (difflib), with size guard |
| `tritobol_app/export.py` | create-new-only export with filename sanitising |
| `tritobol_app/files.py` | strict UTF-8 file decoding |
| `static/js/lib.js` | pure helpers (formatting, validation, history, diff view-model) |

## API
- `GET /api/health`, `GET /api/tokenizers`, `POST /api/tokenizers/upload`
- `POST /api/load-file` (multipart), `POST /api/optimize`, `POST /api/export`
- Success `{"ok": true, ...}`; failure `{"ok": false, "error": {"code","message","field"}}`
- Codes: `validation_error`, `input_too_large`, `file_error`, `tokenizer_error`, `budget_error`,
  `processing_error`, `export_error`, `forbidden`, `not_found`.

## Decisions
- Flask + vanilla JS: one extra dependency, no Node needed by judges.
- Budget = the engine's tail window; the app re-counts the output to verify and reports the result.
- Diff is line-level with word-level detail for paired changed lines; skipped above a size guard.
- Custom tokenizers live in memory only (max 3); temp files are deleted in `finally`.
- Diff uses difflib with `autojunk` (same default as the CLI `--diff`) plus a 5 s cooperative time limit and a 60,000-line cap; otherwise it reports "Diff skipped".
- Engine: `tail()` raises `BudgetTooSmallError` (a ValueError) instead of IndexError for budgets smaller than one character's tokens.
- Security: Host/Origin checks, per-run token on POSTs, CSP `default-src 'self'`.
