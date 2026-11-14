---
inclusion: always
---
# Privacy steering
- Processing is local. Text is never logged by the server or sent to a remote service.
- Never log request bodies. The server does not persist prompt text.
- Browser storage may hold settings and numeric run statistics. Original and optimized prompt text may be persisted only after the user chooses "Save to history" and confirms; this is local to the browser profile and app address and is not synced.
- Warn before saving that browser local storage is not encrypted by Tritobol and may be readable by anyone with access to that browser profile. Never save prompt text automatically.
- Keep saved prompt history versioned and bounded, report storage/read/validation failures, and provide per-entry deletion and clear-history controls.
- Secret detection is pattern-based and incomplete. Always keep that limitation visible; never claim complete detection.
- Never display or log matched secret values.
