# Kiro development evidence — Tritobol Team

**Team structure and roles (main branch):**

| Team member | Role | Tools used |
|---|---|---|
| **William** | Team admin, CLI app developer, visual effects designer | Kiro IDE (deep usage), Kiro crew, GitHub Copilot — for brainstorming, coding, creating artifacts, and maintaining the repository |
| **Rahma Shahbaz** | Web app developer, Kiro evidence documentation | Web app development and documentation |
| **Shadow** | Demo video/presentation conductor, deployment helper | OpenStudio, CapCut, and other video/editing tools |

## William's Kiro usage (CLI app development and visual effects)

William used Kiro IDE deeply throughout the project:
- **Brainstorming:** Collaborated with the Kiro crew to explore ideas for the CLI app and visual effects
- **Coding:** Used Kiro IDE for day-to-day development of the Tritobol CLI application
- **Artifact creation:** Created and maintained Kiro specs, steering documents, and hooks through the IDE
- **Repository maintenance:** Used Kiro IDE to manage the project structure and codebase

The Kiro crew provided real-time guidance during development, especially for visual effects and learning new agent functions and coding languages.

## Artifacts present (files that exist)

| File | What it is |
|---|---|
| `.kiro/specs/application/requirements.md` | 10 requirements with EARS-style acceptance criteria (R1–R10) |
| `.kiro/specs/application/design.md` | architecture, modules, API, design decisions (updated to match the final implementation) |
| `.kiro/specs/application/tasks.md` | task list; items 1–10 ticked only after verification; 11 (Windows) and 12 (run in Kiro) are open |
| `.kiro/steering/{architecture,coding-standards,privacy,testing}.md` | always-included conventions that the implementation follows |
| `.kiro/hooks/*.kiro.hook` (3) | run backend tests on app change; guard against engine edits; run frontend tests on JS change |

## Was the content verified against the code?

- Requirements/design/tasks were reviewed against the final implementation at delivery time (2026-11-12); design.md was updated for the diff time-limit, the engine `BudgetTooSmallError` change and the security guards.
- Hook files use Kiro's `.kiro.hook` JSON layout (`when`/`then`, `fileEdited` trigger, `askAgent` action) as authored through Kiro IDE.

## Test evidence

See `docs/IMPLEMENTATION_REPORT.md` for exact commands and counts (executed 2026-11-12, Linux).
