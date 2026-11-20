---
inclusion: always
---
# Architecture steering
- `tritobol/` is the single source of truth for optimization. Never edit its behaviour for UI needs and never reimplement dedupe, trimming, or windowing in `tritobol_app/` or JavaScript.
- `tritobol_app/` is a thin adapter: validate, call the engine, shape JSON.
- Frontend is vanilla ES modules with no build step. Pure logic goes in `static/js/lib.js` so it is testable with `node --test`.
- Server binds to 127.0.0.1 only. No outbound network calls, no CDN assets, no web fonts.
- Do not break the CLI (`python -m tritobol`) or existing tests in `tests/`.
