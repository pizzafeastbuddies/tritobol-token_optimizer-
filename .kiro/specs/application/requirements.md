# Requirements — Tritobol Application (local web UI)

> Authoring note: these spec files were drafted by Claude (outside the Kiro IDE) for Rahma Shahbaz.
> They follow Kiro's spec layout (requirements -> design -> tasks). See `docs/KIRO_EVIDENCE.md`
> for what has and has not been executed inside Kiro.

## Introduction
Tritobol Application is a local-first web interface over the existing deterministic `tritobol`
optimizer. The engine stays the single source of truth; the application adds validation, a JSON API,
a browser UI, a diff view, analytics and safe export. No text leaves the user's machine.

## Requirements

### R1 — Text input
**User story:** As a user who does not know Python, I want to paste or load text so I can optimize it.
1. WHEN the user pastes or types text THEN the system SHALL show a live character count.
2. WHEN the user loads a file THEN the system SHALL accept only UTF-8 text-like files and place the content in the editor without discarding any of it.
3. WHEN the file is empty, binary, not UTF-8, unsupported or larger than 2 MB THEN the system SHALL show a specific error and leave the existing editor content unchanged.
4. WHEN input exceeds 2 MB (UTF-8 bytes) THEN the system SHALL refuse to optimize and state the limit.
5. WHEN the user clicks Clear THEN the editor SHALL be emptied and no file on disk SHALL be affected.

### R2 — Optimization through the existing engine
1. WHEN the user submits text THEN the backend SHALL call `tritobol.Tritobol.optimize` and SHALL NOT reimplement any optimization logic.
2. The backend SHALL call the engine with `warn_on_truncation=False` and return the warning in JSON.
3. Identical input and options SHALL give identical output (determinism of the engine is preserved).
4. IF the engine raises THEN the system SHALL return a structured error, never a fabricated success.

### R3 — Tokenizer selection
1. The system SHALL list only tokenizers that exist: the bundled DeepSeek V4.1 Flash tokenizer and tokenizers the user uploaded this session.
2. IF a tokenizer cannot initialise THEN it SHALL be shown as unavailable with the reason.
3. WHEN the user uploads a `tokenizer.json` THEN the system SHALL enforce a size limit, validate it by loading it, delete any temporary file, and report failures clearly.
4. The UI SHALL state that counts exclude chat templates and provider/API overhead.

### R4 — Token budget
1. The budget is optional. Values that are not positive integers SHALL be rejected (backend and UI).
2. WHEN a budget is set THEN the engine's sliding window keeps the newest tokens; the UI SHALL say older text is discarded.
3. The response SHALL report whether the output was verified to be within the budget by re-counting.

### R5 — Results and analytics
1. The UI SHALL show original tokens, optimized tokens, saved tokens and reduction percentage exactly as computed by the engine.
2. IF savings are zero or negative THEN the true value SHALL be displayed.
3. Analytics SHALL use only real results from this session; no seeded or fake history.

### R6 — Comparison and diff
1. The UI SHALL show original and optimized text side by side (stacked on mobile).
2. The diff SHALL be computed from the original input and the actual optimizer output.
3. IF the diff is too large to compute safely THEN the system SHALL say so and still show both texts.

### R7 — Truncation transparency
1. WHEN content was discarded by the budget THEN a prominent warning containing the engine's warning text SHALL be shown.
2. The UI SHALL never describe truncated output as fully preserved.

### R8 — Safe export
1. Export SHALL always write a new file; it SHALL never overwrite an existing file or the original input.
2. IF the filename exists THEN the system SHALL choose a new numbered name.
3. Permission and disk errors SHALL be reported with a clear message.
4. A browser download of the optimized text SHALL also be available.

### R9 — Privacy and security
1. The server SHALL bind to 127.0.0.1 only and make no outbound requests.
2. State-changing requests SHALL require a per-run token and a local Host header.
3. The Privacy view SHALL state that secret scanning is pattern-based and incomplete.

### R10 — Compatibility and delivery
1. Existing CLI behaviour and existing tests SHALL remain unchanged and passing.
2. The app SHALL start via `start.bat` on Windows. Windows compatibility SHALL be reported as verified only after verification on Windows.

### R11 — User-controlled local prompt history
1. The application SHALL provide no accounts, OAuth, remote prompt-history service, or cloud sync.
2. A successful optimization SHALL NOT persist either prompt text automatically. Text SHALL be saved only after the user activates "Save to history" and confirms the local-storage disclosure.
3. Each saved item SHALL contain the original prompt, optimized result, timestamp, source label, tokenizer and relevant token/budget statistics, so the user can review it later.
4. The user SHALL be able to review, restore the original into the optimizer, copy the saved result, delete one item, and clear all saved prompt history.
5. Saved prompt text SHALL be stored only in versioned, schema-validated browser local storage, scoped to this browser profile and app address; it SHALL NOT be sent to the server or another device.
6. Before saving, the UI SHALL explain that text is not encrypted by Tritobol, may be visible to others with access to the browser profile, is not synced, and should not include secrets or text the user does not want retained.
7. The UI SHALL show clear empty, unsupported/corrupt-data, unavailable-storage, quota/write-failure and size-limit states. It SHALL not claim a save when persistence fails.
8. Retention SHALL be bounded to 10 entries and 50,000 combined original/result characters per entry. When saving an eleventh item, the oldest saved entry SHALL be removed; a too-large item SHALL be rejected without truncation.
