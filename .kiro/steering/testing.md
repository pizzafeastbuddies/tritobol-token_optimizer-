---
inclusion: always
---
# Testing steering
- Backend: `python -m pytest tests tests_app -q`. Frontend helpers: `node --test`.
- Only claim a test passed if it was executed; report real output.
- Do not assume engine properties that are not guaranteed (e.g. savings are not always positive).
- Export tests must prove the original file is byte-identical and existing files are never overwritten.
