"""Local accounts in SQLite. Prompt text is never written here."""

from __future__ import annotations

import hashlib
import hmac
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .schemas import AppError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ATTEMPT_LIMIT = 8
_ATTEMPT_WINDOW = 15 * 60
CREATED_MESSAGE = "Your account has been created successfully. Please sign in."


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise AppError("validation_error", "Enter your full name.", field="name")
    if len(name) > 80:
        raise AppError("validation_error", "Use 80 characters or fewer.", field="name")
    if any(ord(ch) < 32 for ch in name):
        raise AppError("validation_error", "Enter your full name.", field="name")
    return name


def _clean_email(value: object) -> str:
    email = str(value or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL.match(email):
        raise AppError("validation_error", "Enter an email address with a name and a domain.", field="email")
    return email


def _password_problems(password: object) -> list[str]:
    text = str(password or "")
    problems = []
    if len(text) < 12:
        problems.append("Use at least 12 characters.")
    if not any(ch.islower() for ch in text) or not any(ch.isupper() for ch in text):
        problems.append("Use both upper and lower case letters.")
    if not any(ch.isdigit() for ch in text):
        problems.append("Use at least one number.")
    if len(text) > 200:
        problems.append("Use 200 characters or fewer.")
    return problems


def validate_new_password(password: object, confirm: object, *, field: str = "password") -> str:
    text = str(password or "")
    problems = _password_problems(text)
    if problems:
        raise AppError("validation_error", " ".join(problems), field=field)
    if text != str(confirm or ""):
        raise AppError("validation_error", "Those passwords do not match.", field="confirm")
    return text


def public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def password_tag(secret: str, password_hash: str) -> str:
    return hmac.new(secret.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


class AttemptLimiter:
    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def too_many(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._failures.get(key, []) if now - stamp < _ATTEMPT_WINDOW]
            self._failures[key] = recent
            return len(recent) >= _ATTEMPT_LIMIT

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._failures.get(key, []) if now - stamp < _ATTEMPT_WINDOW]
            recent.append(now)
            self._failures[key] = recent

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class AccountStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.attempts = AttemptLimiter()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL CHECK (length(full_name) BETWEEN 1 AND 80),
                    email TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)")

    def register(self, name: object, email: object, password: object, confirm: object) -> dict:
        full_name = _clean_name(name)
        address = _clean_email(email)
        secret = validate_new_password(password, confirm)
        digest = generate_password_hash(secret, method="scrypt")
        stamp = _now()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (full_name, email, password_hash, created_at, updated_at, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (full_name, address, digest, stamp, stamp),
                )
                row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise AppError("conflict", "An account with that email already exists.", field="email", status=409) from None
        return public_user(row)

    def _by_email(self, conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def authenticate(self, email: object, password: object, remote_key: str) -> sqlite3.Row:
        address = str(email or "").strip().lower()
        secret = str(password or "")
        keys = [f"email:{address}", f"ip:{remote_key}"]
        if any(self.attempts.too_many(key) for key in keys):
            raise AppError("rate_limited", "Too many sign-in attempts. Wait a few minutes and try again.", status=429)
        if not address or not secret:
            raise AppError("unauthorized", "Email or password is incorrect.", status=401)
        with self._connect() as conn:
            row = self._by_email(conn, address)
        valid = bool(row and row["is_active"] and check_password_hash(row["password_hash"], secret))
        if not valid:
            for key in keys:
                self.attempts.fail(key)
            raise AppError("unauthorized", "Email or password is incorrect.", status=401)
        for key in keys:
            self.attempts.clear(key)
        return row

    def get(self, user_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def change_password(self, user_id: int, current: object, new_password: object, confirm: object) -> sqlite3.Row:
        secret = validate_new_password(new_password, confirm, field="new_password")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not row["is_active"] or not check_password_hash(row["password_hash"], str(current or "")):
                raise AppError("unauthorized", "The current password is incorrect.", field="current_password", status=401)
            digest = generate_password_hash(secret, method="scrypt")
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (digest, _now(), user_id),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return updated
