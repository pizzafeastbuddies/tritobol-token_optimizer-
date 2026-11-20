# Kiro development evidence — Rahma Shahbaz (application layer)

**Read this first.** This file separates what exists in the repository from what Kiro actually did.
Nothing below claims that Kiro IDE ran any task, spec or hook. The artifacts were **authored by Claude (an AI assistant, outside
the Kiro IDE) in a chat session** for Rahma, using the Kiro file layout. Rahma should run the steps in "To generate genuine
Kiro evidence" inside Kiro and record the results in the log below before this is presented as Kiro-assisted work.

## Artifacts present (files that exist)
| File | What it is |
|---|---|
| `.kiro/specs/application/requirements.md` | 10 requirements with EARS-style acceptance criteria (R1–R10) |
| `.kiro/specs/application/design.md` | architecture, modules, API, design decisions (updated to match the final implementation) |
| `.kiro/specs/application/tasks.md` | task list; items 1–10 ticked only after verification; 11 (Windows) and 12 (run in Kiro) are open |
| `.kiro/steering/{architecture,coding-standards,privacy,testing}.md` | always-included conventions that the implementation follows |
| `.kiro/hooks/*.kiro.hook` (3) | run backend tests on app change; guard against engine edits; run frontend tests on JS change |

## Was the content verified against the code?
- Requirements/design/tasks were reviewed against the final implementation at delivery time (2026-11-12); design.md was updated for the
  diff time-limit, the engine `BudgetTooSmallError` change and the security guards.
- Hook files use Kiro's `.kiro.hook` JSON layout (`when`/`then`, `fileEdited` trigger, `askAgent` action) as best known to the
  author; **they have not been loaded or triggered in Kiro**, so their exact schema acceptance is unverified.

## Genuine usage log (to be completed by Rahma inside Kiro)
| Date | Kiro feature | What was done in Kiro | Result / evidence (screenshot, commit) |
|---|---|---|---|
| | Spec opened | Open `.kiro/specs/application` and confirm Kiro lists the three documents | |
| | Task executed | Run a task from `tasks.md` (e.g. extend a test) via Kiro | |
| | Steering applied | Ask Kiro for a change and confirm it follows `steering/` rules | |
| | Hook fired | Edit a file in `tritobol_app/`; confirm the hook runs the tests | |
| | Tests run | Kiro-run test command and its output | |

## Test evidence that exists independently of Kiro (executed 2026-11-12, Linux)
See `docs/IMPLEMENTATION_REPORT.md` for exact commands and counts.

## To generate genuine Kiro evidence
1. Open the project folder in Kiro; check *Specs*, *Steering* and *Agent Hooks* panels list the files above.
2. Run `tasks.md` items you want to demonstrate (e.g. "add a test for X") through Kiro; keep the session transcript.
3. Save a file under `tritobol_app/` and confirm the hook triggers; screenshot it.
4. Record dates, prompts and outcomes in the table above. Do not describe anything Kiro did not do.
