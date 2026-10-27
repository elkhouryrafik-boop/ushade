"""Supplier onboarding + profiles (MKT-01) — SQLite-backed registry.

A real owner-side account, not a scraped page. Keyed on the same ``supplier_id`` slug the
catalog and holds use (``catalog.supplier_slug``), so a supplier who onboards immediately
owns the listings already attributed to them by the harvest pipeline and sees the holds
placed against their stock (``GET /api/marketplace/holds/incoming``).

Trust is HONEST: a freshly onboarded supplier is ``verified = False`` until a human admin
verifies them — the UI must never render an unverified supplier as "verified" (that is the
fabricated-trust trap the design review flagged). karpathy: one table + plain upserts.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class SupplierError(RuntimeError):
    """Base for supplier-registry failures."""


class SupplierNotFound(SupplierError):
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    contact_email TEXT NOT NULL DEFAULT '',
    town          TEXT NOT NULL DEFAULT '',
    verified      INTEGER NOT NULL DEFAULT 0,   -- 0/1; human-admin gate, never self-asserted
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


class SupplierStore:
    """Supplier profiles in the shared marketplace DB (own connection; WAL-safe)."""

    def __init__(self, db_path: str | Path = "marketplace.db"):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def register(self, supplier_id: str, *, name: str, contact_email: str = "",
                 town: str = "", verified: bool = False) -> dict:
        """Create or update a supplier profile (idempotent upsert). ``verified`` defaults
        False — onboarding never self-asserts trust."""
        now = _utcnow_iso()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "INSERT INTO suppliers (supplier_id, name, contact_email, town, verified, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(supplier_id) DO UPDATE SET name=excluded.name, "
                    "contact_email=excluded.contact_email, town=excluded.town, updated_at=excluded.updated_at",
                    (supplier_id, name, contact_email, town, 1 if verified else 0, now, now),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return self.get(supplier_id)

    def set_verified(self, supplier_id: str, verified: bool) -> dict:
        """Admin-only trust flip (kept separate from register so onboarding can't self-verify)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE suppliers SET verified = ?, updated_at = ? WHERE supplier_id = ?",
                (1 if verified else 0, _utcnow_iso(), supplier_id),
            )
            if cur.rowcount == 0:
                raise SupplierNotFound(supplier_id)
        return self.get(supplier_id)

    def get(self, supplier_id: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM suppliers WHERE supplier_id = ?", (supplier_id,)
        ).fetchone()
        if row is None:
            raise SupplierNotFound(supplier_id)
        return self._hydrate(row)

    def list(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["verified"] = bool(d["verified"])
        return d
