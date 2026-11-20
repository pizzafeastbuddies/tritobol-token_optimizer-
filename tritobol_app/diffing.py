"""Diff built from the original input and the *actual* optimizer output (difflib).

The diff is computed from the two real strings, so every "removed" or "kept" line is a statement about
those strings, never about a guess of what the engine did. A cooperative time limit protects the server
from pathological inputs; when it trips, the diff is reported as unavailable instead of being faked.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import List, Optional

MAX_DIFF_LINES = 60_000          # per side
DIFF_TIME_LIMIT_S = 5.0          # overall budget for line + word diffs
MAX_WORD_DIFF_CHARS = 2_000      # per paired line
_WORD_RE = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


class _DiffTimeout(Exception):
    pass


class _BoundedMatcher(difflib.SequenceMatcher):
    """SequenceMatcher that gives up once a deadline has passed."""

    def __init__(self, a, b, deadline: float) -> None:
        self._deadline = deadline
        super().__init__(None, a, b)  # autojunk stays on: same default as `python -m tritobol --diff`

    def find_longest_match(self, *args, **kwargs):
        if time.monotonic() > self._deadline:
            raise _DiffTimeout
        return super().find_longest_match(*args, **kwargs)


def _word_ops(a: str, b: str, deadline: float) -> Optional[List[dict]]:
    ta, tb = _WORD_RE.findall(a), _WORD_RE.findall(b)
    try:
        ops = _BoundedMatcher(ta, tb, deadline).get_opcodes()
    except _DiffTimeout:
        return None
    return [{"t": tag, "a": "".join(ta[i1:i2]), "b": "".join(tb[j1:j2])} for tag, i1, i2, j1, j2 in ops]


def build_diff(original: str, optimized: str) -> dict:
    a = original.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    b = optimized.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if original == optimized:
        return {"available": True, "identical": True, "ops": [], "summary": _summary(a, b, [])}
    if len(a) > MAX_DIFF_LINES or len(b) > MAX_DIFF_LINES:
        return _unavailable(
            f"Diff skipped: more than {MAX_DIFF_LINES:,} lines to compare. "
        )
    deadline = time.monotonic() + DIFF_TIME_LIMIT_S
    try:
        opcodes = _BoundedMatcher(a, b, deadline).get_opcodes()
    except _DiffTimeout:
        return _unavailable("Diff skipped: the comparison took too long for this input. ")

    ops: List[dict] = []
    for tag, i1, i2, j1, j2 in opcodes:
        op = {"tag": tag, "a": a[i1:i2], "a_start": i1 + 1, "b_start": j1 + 1}
        if tag != "equal":  # equal runs are sent once; the other side is identical by definition
            op["b"] = b[j1:j2]
        if tag == "replace" and (i2 - i1) == (j2 - j1) and (i2 - i1) <= 200:
            op["words"] = [
                _word_ops(x, y, deadline) if len(x) <= MAX_WORD_DIFF_CHARS and len(y) <= MAX_WORD_DIFF_CHARS else None
                for x, y in zip(a[i1:i2], b[j1:j2])
            ]
        ops.append(op)
    return {"available": True, "identical": False, "ops": ops, "summary": _summary(a, b, ops)}


def _unavailable(reason: str) -> dict:
    return {
        "available": False, "identical": False, "ops": [],
        "reason": reason + "Original and optimized text and all token statistics are still shown.",
    }


def _summary(a: List[str], b: List[str], ops: List[dict]) -> dict:
    removed = sum(len(o["a"]) for o in ops if o["tag"] in ("delete", "replace"))
    added = sum(len(o["b"]) for o in ops if o["tag"] in ("insert", "replace"))
    kept = sum(len(o["a"]) for o in ops if o["tag"] == "equal") if ops else len(a)
    return {
        "original_lines": len(a), "optimized_lines": len(b),
        "lines_removed_or_changed": removed, "lines_added_or_changed": added, "lines_unchanged": kept,
    }
