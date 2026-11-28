"""Local, redaction-safe detection of personal data: emails, phones and names.

Findings carry kind and position only. They never store the matched text.

Name detection is list based. It finds ``First Last`` and ``First Middle Last``
when every part is a known name. It does not find names missing from the lists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

EMAIL = "EMAIL"
PHONE = "PHONE"
PERSONAL_NAME = "PERSONAL_NAME"


def _load_names(filename: str) -> frozenset[str]:
    """Read one capitalized name per line from the bundled ``data`` folder."""
    text = (
        resources.files("tritobol")
        .joinpath("data", filename)
        .read_text(encoding="utf-8")
    )
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


# Starter lists in tritobol/data/. Add a name by adding a line to the file.
FIRST_NAMES = _load_names("first_names.txt")
LAST_NAMES = _load_names("last_names.txt")

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
# "git@github.com:org/repo.git" is an SSH remote, not an email address.
_SSH_REMOTE_RE = re.compile(r":[^\s:]")
# One capitalized word. Covers Latin letters with accents (Mueller, Garcia,
# Yilmaz and so on).
_UPPER = r"A-Z\u00c0-\u00d6\u00d8-\u00de\u0100-\u017f"
_LOWER = r"a-z\u00df-\u00f6\u00f8-\u00ff\u0100-\u017f"
_WORD_RE = re.compile(rf"(?<!\w)[{_UPPER}][{_LOWER}]+(?!\w)")
# Digits with common separators. Candidates are checked by _is_phone.
_PHONE_CANDIDATE_RE = re.compile(r"(?<![\w.+-])\+?\(?\d(?:[\d\s().-]*\d)?(?!\w)")
_DATE_RE = re.compile(
    r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4}"
)
_VERSION_OR_IP_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){2,}")


@dataclass(frozen=True)
class PersonalDataFinding:
    """Personal-data match metadata; deliberately excludes the matched text."""

    kind: str
    start: int
    end: int


def _is_phone(candidate: str) -> bool:
    text = candidate.strip()
    digit_count = sum(char.isdigit() for char in text)
    if not 7 <= digit_count <= 15:
        return False
    if _DATE_RE.fullmatch(text) or _VERSION_OR_IP_RE.fullmatch(text):
        return False
    # A short run of bare digits (order IDs, counters) is not a phone unless
    # it has a leading 0 (national trunk prefix). Known limit: bare
    # 8-digit numbers such as Singapore's are not detected.
    if text.isdigit() and len(text) < 10 and not text.startswith("0"):
        return False
    return True


def _find_names(text: str) -> list[tuple[int, int, str]]:
    """Find known ``First Last`` and ``First Middle Last`` name sequences."""
    words = [(m.start(), m.end(), m.group()) for m in _WORD_RE.finditer(text)]
    found: list[tuple[int, int, str]] = []
    index = 0
    while index < len(words):
        s0, e0, w0 = words[index]
        if w0 in FIRST_NAMES and index + 1 < len(words):
            s1, e1, w1 = words[index + 1]
            if text[e0:s1] == " ":
                if (
                    w1 in FIRST_NAMES
                    and index + 2 < len(words)
                    and text[e1:words[index + 2][0]] == " "
                    and words[index + 2][2] in LAST_NAMES
                ):
                    found.append((s0, words[index + 2][1], PERSONAL_NAME))
                    index += 3
                    continue
                if w1 in LAST_NAMES:
                    found.append((s0, e1, PERSONAL_NAME))
                    index += 2
                    continue
        index += 1
    return found


def find_personal_data(text: str) -> list[PersonalDataFinding]:
    """Return ordered, non-overlapping personal-data findings in ``text``."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    candidates: list[tuple[int, int, str]] = [
        (match.start(), match.end(), EMAIL)
        for match in _EMAIL_RE.finditer(text)
        if not _SSH_REMOTE_RE.match(text, match.end())
    ]
    candidates.extend(_find_names(text))
    for match in _PHONE_CANDIDATE_RE.finditer(text):
        if _is_phone(match.group(0)):
            candidates.append((match.start(), match.end(), PHONE))

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    findings: list[PersonalDataFinding] = []
    last_end = -1
    for start, end, kind in candidates:
        if start < last_end:
            continue
        findings.append(PersonalDataFinding(kind, start, end))
        last_end = end
    return findings
