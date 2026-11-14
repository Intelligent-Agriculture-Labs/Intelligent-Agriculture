"""Account-free farm sync between devices (phone <-> PC).

A farm is a JSON document stored in SQLite, addressed by a random 128-bit farm_id (kept secret on each device)
and a short human-readable sync code for pairing another device. Fields are merged per id: the newer
`updated_at` wins; deletions are tombstones. Settings merge as a whole by the farm's last write.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(
    os.environ.get(
        "FIELDSHIFT_DB",
        Path(os.environ.get("FIELDSHIFT_CACHE_DIR", Path(__file__).resolve().parents[2] / ".cache"))
        / "farms.sqlite",
    )
)
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O/1/I confusion
_lock = threading.Lock()
MAX_FIELDS = 200
MAX_DOC_BYTES = 2_000_000


class FarmNotFound(KeyError):
    pass


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute(
        "CREATE TABLE IF NOT EXISTS farms (farm_id TEXT PRIMARY KEY, sync_code TEXT UNIQUE, doc TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)"
    )
    return c


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _new_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    c = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{c[:4]}-{c[4:8]}" if len(c) == 8 else code.upper()


def merge_fields(server: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-field last-writer-wins on updated_at (ISO strings compare chronologically when same format)."""
    by_id = {f["id"]: f for f in server}
    for f in incoming:
        fid = f.get("id")
        if not fid:
            continue
        cur = by_id.get(fid)
        if cur is None or str(f.get("updated_at", "")) >= str(cur.get("updated_at", "")):
            by_id[fid] = f
    return sorted(by_id.values(), key=lambda f: str(f.get("updated_at", "")))


def _row_to_farm(row: tuple[str, str, str, int, str]) -> dict[str, Any]:
    farm_id, code, doc, version, updated = row
    d = json.loads(doc)
    return {
        "farm_id": farm_id,
        "sync_code": code,
        "name": d.get("name", "My farm"),
        "fields": d.get("fields", []),
        "settings": d.get("settings", {}),
        "version": version,
        "updated_at": updated,
    }


def _validate(fields: list[dict[str, Any]]) -> None:
    if len(fields) > MAX_FIELDS:
        raise ValueError(f"too many fields (max {MAX_FIELDS})")
    if len(json.dumps(fields)) > MAX_DOC_BYTES:
        raise ValueError("farm document too large")


def create(
    name: str | None, fields: list[dict[str, Any]] | None, settings: dict[str, Any] | None
) -> dict[str, Any]:
    fields = fields or []
    _validate(fields)
    farm_id = uuid.uuid4().hex
    with _lock, _conn() as c:
        for _ in range(10):
            code = _new_code()
            try:
                c.execute(
                    "INSERT INTO farms VALUES (?,?,?,?,?)",
                    (
                        farm_id,
                        code,
                        json.dumps({"name": name or "My farm", "fields": fields, "settings": settings or {}}),
                        1,
                        _now(),
                    ),
                )
                break
            except sqlite3.IntegrityError:
                continue
        row = c.execute("SELECT * FROM farms WHERE farm_id=?", (farm_id,)).fetchone()
    return _row_to_farm(row)


def get(farm_id: str) -> dict[str, Any]:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM farms WHERE farm_id=?", (farm_id,)).fetchone()
    if not row:
        raise FarmNotFound(farm_id)
    return _row_to_farm(row)


def join(code: str) -> dict[str, Any]:
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM farms WHERE sync_code=?", (normalize_code(code),)).fetchone()
    if not row:
        raise FarmNotFound(code)
    return _row_to_farm(row)


def push(
    farm_id: str, name: str | None, fields: list[dict[str, Any]], settings: dict[str, Any] | None
) -> dict[str, Any]:
    _validate(fields)
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM farms WHERE farm_id=?", (farm_id,)).fetchone()
        if not row:
            raise FarmNotFound(farm_id)
        cur = _row_to_farm(row)
        merged = merge_fields(cur["fields"], fields)
        doc = {
            "name": name or cur["name"],
            "fields": merged,
            "settings": {**cur["settings"], **(settings or {})},
        }
        c.execute(
            "UPDATE farms SET doc=?, version=version+1, updated_at=? WHERE farm_id=?",
            (json.dumps(doc), _now(), farm_id),
        )
        row = c.execute("SELECT * FROM farms WHERE farm_id=?", (farm_id,)).fetchone()
    return _row_to_farm(row)
