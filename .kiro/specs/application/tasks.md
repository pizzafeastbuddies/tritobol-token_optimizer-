# Tasks — Tritobol Application

Status is updated only after the work is actually done and verified.

- [x] 1. Repository audit (existing engine, CLI, 40 tests passing)
- [x] 2. Kiro spec, steering, hooks drafted (authored outside Kiro; not yet executed inside Kiro IDE)
- [x] 3. schemas + service + tokenizer registry
- [x] 4. diffing, export, file loading
- [x] 5. Flask routes, guards, error handlers
- [x] 6. Frontend: dashboard, optimizer, results, diff, analytics, privacy, settings
- [x] 7. Backend tests (`tests_app/`), including hypothesis property tests
- [x] 8. Frontend tests (`frontend_tests/`, Node runner + jsdom) and real-browser tests (`tests_e2e/`, Playwright)
- [x] 9. Integration test: paste -> tokenizer -> budget -> optimize -> diff -> export -> original unchanged
- [x] 10. `start.bat`, README for the app, packaging notes
- [ ] 11. Windows verification (to be done by Rahma on Windows 10)
- [ ] 12. Run specs/hooks inside Kiro IDE and fill in `docs/KIRO_EVIDENCE.md`

## Notes
- Engine: `tail()` IndexError fixed as `BudgetTooSmallError` (see docs/APPLICATION.md, "Engine change").
- Tasks 11 and 12 require Rahma on Windows 10 / in the Kiro IDE and are intentionally open.
