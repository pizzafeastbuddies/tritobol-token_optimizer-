"""Local, redaction-safe detection of personal data: emails, phones and names.

Findings carry kind and position only. They never store the matched text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL = "EMAIL"
PHONE = "PHONE"
PERSONAL_NAME = "PERSONAL_NAME"

# Small starter lists. Names are capitalized, as they appear in text.
FIRST_NAMES = frozenset(
    {
        "Aiden", "Ahmed", "Ali", "Amit", "Andrew", "Anna", "Anthony", "Ava",
        "Ashley", "Barbara", "Charles", "Chen", "Daniel", "David", "Donald",
        "Elizabeth", "Emily", "Emma", "Ethan", "Hannah", "Hui", "James",
        "Jennifer", "Jessica", "John", "Joseph", "Joshua", "Jun", "Karen",
        "Kenneth", "Li", "Lisa", "Linda", "Liam", "Lucas", "Mark", "Mary",
        "Matthew", "Mei", "Michael", "Ming", "Mia", "Mohammed", "Nancy",
        "Noah", "Olivia", "Patricia", "Paul", "Priya", "Raj", "Richard",
        "Robert", "Sarah", "Sofia", "Steven", "Susan", "Thomas", "William",
        "Wei", "Yan",
    }
)

LAST_NAMES = frozenset(
    {
        "Adams", "Allen", "Anderson", "Ali", "Baker", "Brown", "Campbell",
        "Carter", "Chen", "Choi", "Clark", "Costa", "Davis", "Flores",
        "Garcia", "Gonzalez", "Green", "Hall", "Harris", "Hernandez", "Hill",
        "Huang", "Jackson", "Johnson", "Jones", "Khan", "Kim", "King", "Kowalski",
        "Kumar", "Lee", "Lewis", "Li", "Liu", "Lopez", "Martin", "Martinez",
        "Miller", "Mitchell", "Moore", "Muller", "Nelson", "Ng", "Nguyen",
        "Park", "Patel", "Perez", "Ramirez", "Rivera", "Roberts", "Robinson",
        "Rodriguez", "Rossi", "Sanchez", "Santos", "Schmidt", "Scott", "Shah",
        "Silva", "Singh", "Smith", "Taylor", "Thompson", "Torres", "Walker",
        "Wang", "White", "Williams", "Wilson", "Wong", "Wright", "Wu", "Yang",
        "Young", "Zhang", "Zhao", "Zhou",
    }
)

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
# Zero-width lookahead so that "Ask John Smith" still finds "John Smith".
# "git@github.com:org/repo.git" is an SSH remote, not an email address.
_SSH_REMOTE_RE = re.compile(r":[^\s:]")
_NAME_RE = re.compile(r"(?=\b([A-Z][a-z]+) ([A-Z][a-z]+)\b)")
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


def find_personal_data(text: str) -> list[PersonalDataFinding]:
    """Return ordered, non-overlapping personal-data findings in ``text``."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    candidates: list[tuple[int, int, str]] = [
        (match.start(), match.end(), EMAIL)
        for match in _EMAIL_RE.finditer(text)
        if not _SSH_REMOTE_RE.match(text, match.end())
    ]
    for match in _NAME_RE.finditer(text):
        first, last = match.group(1), match.group(2)
        if first in FIRST_NAMES and last in LAST_NAMES:
            start = match.start()
            end = start + len(first) + 1 + len(last)
            candidates.append((start, end, PERSONAL_NAME))
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
