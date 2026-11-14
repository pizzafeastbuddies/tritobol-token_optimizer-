# Tritobol App Requirements

## Status

Draft for team review. This describes a proposed application around the existing Tritobol Python package; it does not describe an implemented app.

## Verified product baseline

- The repository currently contains a Python package and CLI, not a graphical application. The guided CLI accepts one UTF-8 text file, optionally applies a token budget, shows token counts and a unified diff, and requires confirmation before saving to a separate file.
- `Tritobol.optimize()` deterministically cleans repeated content and formatting noise, applies conservative handling to supported code/configuration blocks, and optionally keeps the newest token window when a hard budget is exceeded. It does not summarize or rewrite content using a model.
- The default tokenizer is bundled DeepSeek V4.1 Flash. Callers may provide a compatible local Hugging Face `tokenizer.json`; token counts cover supplied text only, not provider chat templates, tools, message framing, or API overhead.
- Existing project/file processing is implemented in `tritobol/batch.py`. It writes a separate output tree, skips symbolic links, applies `.gitignore` rules by default, copies unsupported file types unchanged, and rolls back supported code/configuration files when truncation or validation would make them unsafe.
- Sensitive-value scanning is pattern-based. Its supported modes are `skip`, `mask`, and `off`; it is not a general detector of confidential prose. Segment logs do not include detected sensitive values.
- The current guided CLI reads and writes files locally, and the inspected optimizer/tokenizer paths do not call a model or provider API. A future app's packaging and runtime architecture have not yet been selected.
- The root has no existing `.kiro` directory. `.gitignore` does not exclude `.kiro`; an MIT license file and matching package license metadata are present.

## Goal and scope

Deliver a polished, accessible MVP that lets a user inspect and control Tritobol optimization of one text input. Keep the existing Python optimizer as the source of truth. This draft scopes the MVP to pasted text and one uploaded UTF-8 text file; project-tree processing is not required in the first app release.

The app must not silently change the optimizer's behavior, imply model/API integration, or claim guaranteed token savings, content quality, or comprehensive secret detection.

## Confirmed local prompt history

The user confirmed **no accounts, OAuth, or cloud sync**. Prompt text is saved only when the user explicitly chooses **Save to history** after a successful optimization and confirms the storage warning; it is never saved automatically. Store original and optimized text in versioned browser local storage for later recovery on this browser profile and app address only. The UI must explain that this data is not encrypted by Tritobol and is not synced to a phone or other device. Provide review, restore-original-to-optimizer, copy-result, per-entry delete, and clear-history actions. Keep at most 10 entries and reject an entry whose original and optimized texts exceed 50,000 combined characters; never silently truncate a saved result. Show empty, corrupt/unsupported schema, unavailable storage, and quota/write failure states without implying success.

## User stories and acceptance criteria

### Requirement 1: Provide text input

**User story:** As a user, I can paste text or load a UTF-8 text file so I can optimize content I choose.

Acceptance criteria:

1. The input screen offers a multiline paste/edit field and a control to load one UTF-8 text file.
2. A successfully loaded file's text is shown in the editable input field before optimization.
3. Empty or whitespace-only input cannot be optimized; the app explains how to provide text. This is a proposed UX decision because the library itself accepts empty text.
4. An unreadable or invalid UTF-8 file produces a visible, actionable error and leaves the input available for correction; it is not silently replaced with empty text.
5. The app does not write to the selected source file while loading, editing, optimizing, previewing, or cancelling.

### Requirement 2: Configure and run optimization

**User story:** As a user, I can choose a supported tokenizer and optional token budget, then run the existing optimizer.

Acceptance criteria:

1. The bundled DeepSeek V4.1 Flash tokenizer is selected by default.
2. The user can select the bundled tokenizer or supply a compatible local Hugging Face `tokenizer.json`. The app does not download tokenizers or silently fall back to another tokenizer if loading fails.
3. A blank budget means no hard token limit. A supplied budget must be a positive integer; invalid values are rejected before optimization with a clear message.
4. Optimization calls the existing `Tritobol.optimize()` API. The MVP does not send input text to a hosted model, provider API, or other external processing service.
5. The app reports tokenizer-load and optimization failures visibly, preserves the current input, and does not present an error as a successful result.
6. Near token counts and budgets, the app explains that counts cover supplied text only and omit provider-specific chat templates, tools, message framing, and API overhead.

### Requirement 3: Review results and changes

**User story:** As a user, I can understand what changed and whether any content was discarded before exporting.

Acceptance criteria:

1. After a successful run, the app shows the original and optimized text, a readable diff, original and optimized token counts, absolute and percentage savings, and any optimizer warning.
2. When a token window truncates input, the app prominently says that the *earliest* content was discarded, shows the discarded-token count, and makes the retained newest text inspectable before export.
3. If optimization makes no text change, the app says so and presents the unchanged result without implying savings.
4. The app does not claim that all unique content is preserved when a hard token budget can discard earlier text.
5. Any exposed sensitive-data setting maps to the existing `skip`, `mask`, or `off` behavior and describes pattern-scanning limitations. The UI does not promise detection of all secrets or confidential prose.

### Requirement 4: Export without damaging source files

**User story:** As a user, I can save the reviewed result without accidentally replacing my source or another file.

Acceptance criteria:

1. Export is available only after a successful optimization result is ready.
2. Export writes the optimized text as UTF-8 to a separate destination and requires an explicit user action; cancelling leaves files unchanged.
3. The app refuses to overwrite the input source or an existing destination. It reports the conflict and allows the user to choose another destination.
4. Export failure is reported clearly; the source remains unchanged and the app does not show a success state.
5. Tests compare source bytes before and after loading, optimizing, previewing, cancellation, and export, and verify that existing destination bytes remain unchanged on conflict.

### Requirement 5: Accessible, understandable interaction

**User story:** As a user with different access needs, I can operate the complete workflow and understand its status and errors.

Acceptance criteria:

1. All controls and dialogs are operable by keyboard, with a visible focus indicator and a logical focus order.
2. Every input and action has a programmatic label; validation messages are associated with their fields.
3. Loading, optimization, completion, truncation warnings, and errors are announced as status changes to assistive technology without requiring color alone.
4. Text contrast meets WCAG 2.2 AA: at least 4.5:1 for normal text and 3:1 for large text and relevant user-interface boundaries.
5. The diff and result remain readable at supported narrow window sizes and with text zoom; decorative styling never obscures warnings or controls.

### Requirement 6: Handle large inputs predictably

**User story:** As a user, I get clear feedback rather than a hung or crashed app when processing a large input.

Acceptance criteria:

1. While processing, the app shows a busy state, prevents duplicate submissions, and provides a completion or error state.
2. A 1 MiB UTF-8 fixture can be loaded and processed in the evaluation environment without a crash or loss of the original input. Record elapsed time and environment; do not make a latency guarantee until the team sets a benchmark target from measurements.
3. The app communicates any enforced input-size limit before processing. The limit, or whether the MVP needs one, is an unresolved decision below.

## Non-goals for the MVP

- Hosted optimization, provider API calls, model-based rewriting/summarization, or claims of automatic model/provider integration.
- Project-tree or batch processing in the app UI, unless the team explicitly adds it to scope. The Python package already has a separate local project-processing API.
- Guaranteed savings, semantic-equivalence guarantees, or claims that pattern-based sensitive-value scanning catches every secret.

## Focused tests and evaluation

1. **Input:** paste and valid UTF-8 file load; empty and whitespace-only input; missing, unreadable, and invalid-UTF-8 files; verify failed loads do not erase existing text.
2. **Optimizer integration:** verify the bundled and selected local tokenizer are used for counts and optimization; invalid tokenizer JSON produces a visible failure rather than a default-tokenizer fallback.
3. **Budget and truncation:** blank budget, valid positive budget, zero/negative/non-integer rejection, under-budget input, and over-budget input; verify the visible warning, discarded count, newest-context result, and that retained text is within the configured budget.
4. **Change review:** stable diff for a known fixture, unchanged-input state, and preservation fixtures for unique text, protected code, and malformed supported configuration according to existing optimizer behavior.
5. **File safety:** source bytes unchanged throughout the workflow; no write on cancel; source-path and existing-destination conflicts rejected; successful export contains the reviewed optimized UTF-8 text.
6. **Errors and accessibility:** exercise read, tokenizer, optimization, and write errors; keyboard-only completion of the workflow; visible focus, labels, contrast checks, and screen-reader status announcements.
7. **Large input:** process the 1 MiB fixture without a crash, confirm the input remains available, and record environment and elapsed time for a later team-set performance target.

The repository already has focused CLI, optimizer, tokenizer, secret-scanner, and batch tests in `tests/test_cli.py`, `tests/test_tritobol.py`, `tests/test_secrets.py`, and `tests/test_batch.py`. App tests should supplement these rather than replace them.

## Unresolved decisions

- Select the app runtime, UI framework, and packaging/distribution approach that can invoke the existing Python package locally.
- Decide whether the app should support project-tree processing after the single-input MVP.
- Set an input-size limit, if needed, and a performance target only after measuring representative inputs on documented hardware.
- Confirm whether whitespace-only text should remain rejected or be treated as valid input.
- Confirm the export interaction for the chosen runtime (download, save dialog, or another explicit destination flow).
- Confirm the visual direction with the team. A Halloween-inspired **Costume Contest** treatment is a proposal, not a finalized category or design requirement; if selected, it must still meet all readability and accessibility criteria.

## Separate hackathon submission checklist

These are submission checks, not app acceptance criteria. Verify each against the current event rules and submission portal; this draft does not claim they are complete.

- [ ] Confirm the official team roster meets the event's participant limit (the prior planning context mentioned four collaborators; the registered roster is unverified).
- [ ] Confirm the selected category with the team and event rules. Costume Contest remains a proposal until confirmed.
- [ ] Confirm the GitHub repository is public and the open-source license is appropriate; an MIT license file currently exists in this checkout.
- [ ] Keep the `.kiro/` directory at the repository root and verify it is included in the submitted repository; it is not excluded by the current `.gitignore`.
- [ ] Provide a working app URL or clear, tested judge instructions to run the app.
- [ ] Publish a YouTube demo under three minutes that shows the working project and explains Kiro features actually used.
- [ ] Document the Kiro spec-driven workflow and Kiro capabilities actually used; do not claim unperformed usage.
