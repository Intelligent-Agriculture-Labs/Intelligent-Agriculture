"""Email + password accounts. Each account owns one farm (the same document as the account-free sync farms).

Security basics:
* Passwords: scrypt (n=2^14, r=8, p=1, 32-byte key) with a random 16-byte salt; constant-time comparison.
* Sessions: random 256-bit tokens; only their SHA-256 hash is stored; 90-day expiry; logout deletes the session.
* Login rate limit: 8 failures per e-mail per 15 minutes.
* No e-mail verification / password-reset mail in this deployment (no mail server) — documented in LIMITATIONS.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
import uuid
from typing import Any

from . import farms

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_DAYS = 90


class AuthError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _conn() -> sqlite3.Connection:
    c = farms._conn()
    c.execute(
        "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, pw_hash BLOB NOT NULL, "
        "salt BLOB NOT NULL, farm_id TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL)"
    )
    return c


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _user_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {"id": row[0], "email": row[1], "name": row[2] or "", "created_at": row[6]}


def _new_session(c: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = (_now() + dt.timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    c.execute(
        "INSERT INTO sessions VALUES (?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, exp)
    )
    return token


def register(
    email: str,
    password: str,
    name: str | None,
    fields: list[dict[str, Any]] | None,
    settings: dict[str, Any] | None,
) -> dict[str, Any]:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError(422, "Please enter a valid e-mail address.")
    if len(password) < 8:
        raise AuthError(422, "The password needs at least 8 characters.")
    farm = farms.create(f"{(name or email.split('@')[0]).strip()}'s farm", fields, settings)
    salt = secrets.token_bytes(16)
    uid = uuid.uuid4().hex
    with _lock, _conn() as c:
        try:
            c.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?,?)",
                (
                    uid,
                    email,
                    (name or "").strip()[:120],
                    _hash_pw(password, salt),
                    salt,
                    farm["farm_id"],
                    _now().isoformat(timespec="seconds"),
                ),
            )
        except sqlite3.IntegrityError as e:
            raise AuthError(409, "An account with this e-mail already exists. Please log in.") from e
        token = _new_session(c, uid)
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return {"token": token, "user": _user_dict(row), "farm": farm}


def login(email: str, password: str) -> dict[str, Any]:
    email = email.strip().lower()
    now = time.time()
    recent = [t for t in _fails.get(email, []) if now - t < 900]
    if len(recent) >= 8:
        raise AuthError(429, "Too many attempts. Please wait 15 minutes and try again.")
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = row is not None and hmac.compare_digest(_hash_pw(password, row[4]), row[3])
        if not ok:
            _fails[email] = [*recent, now]
            raise AuthError(401, "E-mail or password is not correct.")
        _fails.pop(email, None)
        token = _new_session(c, row[0])
    return {"token": token, "user": _user_dict(row), "farm": farms.get(row[5])}


def user_for_token(token: str | None) -> tuple[dict[str, Any], str]:
    """Returns (user, farm_id) for a valid bearer token."""
    if not token:
        raise AuthError(401, "Please log in.")
    th = hashlib.sha256(token.encode()).hexdigest()
    with _lock, _conn() as c:
        s = c.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash=?", (th,)).fetchone()
        if not s or s[1] < _now().isoformat(timespec="seconds"):
            raise AuthError(401, "Your session has expired. Please log in again.")
        row = c.execute("SELECT * FROM users WHERE id=?", (s[0],)).fetchone()
    if not row:
        raise AuthError(401, "Please log in.")
    return _user_dict(row), row[5]


def logout(token: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def change_password(token: str, old: str, new: str) -> None:
    user, _ = user_for_token(token)
    if len(new) < 8:
        raise AuthError(422, "The new password needs at least 8 characters.")
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not hmac.compare_digest(_hash_pw(old, row[4]), row[3]):
            raise AuthError(401, "The current password is not correct.")
        salt = secrets.token_bytes(16)
        c.execute("UPDATE users SET pw_hash=?, salt=? WHERE id=?", (_hash_pw(new, salt), salt, user["id"]))
        # sign out other devices except this session
        th = hashlib.sha256(token.encode()).hexdigest()
        c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user["id"], th))


def delete_account(token: str, password: str) -> None:
    user, farm_id = user_for_token(token)
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not hmac.compare_digest(_hash_pw(password, row[4]), row[3]):
            raise AuthError(401, "The password is not correct.")
        c.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        c.execute("DELETE FROM users WHERE id=?", (user["id"],))
        c.execute("DELETE FROM farms WHERE farm_id=?", (farm_id,))
