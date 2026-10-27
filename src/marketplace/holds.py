"""Binding-reserve hold store (MKT-03 / MKT-06) — SQLite state machine.

Turns a browsable scraped listing into a claim that BINDS. This is the stateful half of
the Material Recovery Inventory; the harvest half (``src/inventory/``) is read-only
discovery. A hold is a REAL, time-boxed, supplier-confirmable reservation: placing it
decrements the available pool ATOMICALLY (no double-booking, MKT-06), the countdown is a
real ``expires_at`` row (never decorative — XFN-B3 "a claim binds or is labelled
not-a-reservation"), and an expired hold auto-releases its units back to the pool.

The design follows the researched reservation-backend recipe
(``.planning/materials-app/research/backend/03-reservation-backend-patterns.md``):

  * SQLite single-writer: every mutation is a ``BEGIN IMMEDIATE`` write txn, so the
    guarded decrement + insert + event-log write are serialized and atomic.
  * Oversell is impossible via a GUARDED CONDITIONAL UPDATE, never a read-then-write:
    ``UPDATE ... SET available_units = available_units - :qty WHERE ... AND
    available_units >= :qty`` then treat ``rowcount == 0`` as "insufficient stock".
  * LAZY EXPIRY (no scheduler — matches the codebase's no-background-loop discipline):
    a hold is live iff ``state='confirmed'`` OR (``state='requested'`` AND
    ``expires_at > now``); expired ``requested`` holds are reclaimed-on-place inside the
    same txn before a new decrement.
  * IDEMPOTENCY: a client-generated key (UNIQUE) so a retried place-hold returns the
    original hold instead of double-reserving.
  * STATE MACHINE: requested -> confirmed -> collected (happy path); requested -> expired
    (TTL); requested|confirmed -> released (decline/cancel). Every transition is guarded
    (``WHERE state = :expected``) and appends a ``hold_events`` row in the same txn.

State machine::

    [available] --place_hold(atomic decrement)--> requested
                                                     |
        supplier confirm (before expiry) -----------+--> confirmed
                                                     |        |
        TTL expire / decline / cancel                |        | collect
                       v                             v        v
                expired / released (units returned)        collected (terminal, gone)

karpathy: one SQLite file + a handful of guarded transactions. No ORM, no background
reaper, no DAG engine. ``now`` is injectable everywhere so the suite is deterministic
without sleeping.
"""

from __future__ import annotations

import functools
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


def _synchronized(fn):
    """Serialize a public store method on the instance lock.

    The store owns ONE sqlite connection; FastAPI dispatches sync endpoints across a
    threadpool, so two threads could otherwise issue overlapping ``BEGIN IMMEDIATE`` on
    the same connection. A re-entrant lock makes a shared instance thread-safe (the
    cross-PROCESS no-double-book guarantee still comes from SQLite's single-writer lock).
    """

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper

# TTLs (ASSUMED — labelled per XFN-B1; tune per deployment). The supplier-confirm window
# is short (the organiser's units are tied up while awaiting confirmation); the
# collection window is long (a confirmed hold is no longer auto-released).
REQUEST_TTL_S: int = 15 * 60       # 15 min confirm window (ASSUMED)
COLLECT_TTL_S: int = 48 * 3600     # 48 h collection window after confirm (ASSUMED)

# A hold is "live" (ties up inventory) while requested-not-expired or confirmed. Collected
# units are physically gone (NOT returned to the pool); released/expired units return.
_LIVE_STATES = ("requested", "confirmed")


# --------------------------------------------------------------------------- #
# Typed failures (mirror the inventory/climate typed-error discipline)
# --------------------------------------------------------------------------- #
class HoldError(RuntimeError):
    """Base for every marketplace hold failure."""


class InsufficientStock(HoldError):
    """The guarded decrement refused: not enough available units (no double-book)."""

    def __init__(self, listing_id: str, qty: float, available: float):
        super().__init__(
            f"insufficient stock for {listing_id!r}: requested {qty}, available {available}"
        )
        self.listing_id = listing_id
        self.qty = qty
        self.available = available


class UnknownListing(HoldError):
    """No registered listing pool for this id (register_listing was never called)."""


class HoldNotFound(HoldError):
    """No hold with this id."""


class IllegalTransition(HoldError):
    """The hold is not in a state from which this transition is legal (rowcount == 0)."""

    def __init__(self, hold_id: str, want: str, have: str | None):
        super().__init__(
            f"hold {hold_id!r}: illegal transition (need state {want!r}, have {have!r})"
        )
        self.hold_id = hold_id


class IdempotencyConflict(HoldError):
    """Same idempotency key reused with different (listing_id, qty) — Stripe-style guard."""


# --------------------------------------------------------------------------- #
# Time helpers (UTC ISO-8601 everywhere — pitfall 11: never naive/local)
# --------------------------------------------------------------------------- #
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """UTC ISO-8601 with millisecond precision, matching SQLite strftime('%Y-...%fZ')."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS listing_inventory (
    listing_id      TEXT PRIMARY KEY,
    material_id     TEXT NOT NULL DEFAULT '',
    supplier_id     TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT '',
    source_url      TEXT NOT NULL DEFAULT '',
    total_units     REAL NOT NULL CHECK (total_units >= 0),
    available_units REAL NOT NULL CHECK (available_units >= 0),
    version         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS holds (
    id              TEXT PRIMARY KEY,
    listing_id      TEXT NOT NULL REFERENCES listing_inventory(listing_id),
    material_id     TEXT NOT NULL DEFAULT '',
    organiser_id    TEXT NOT NULL,
    supplier_id     TEXT NOT NULL DEFAULT '',
    qty             REAL NOT NULL CHECK (qty > 0),
    unit            TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'requested'
                    CHECK (state IN ('requested','confirmed','collected','released','expired')),
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    confirmed_at    TEXT,
    released_at     TEXT,
    release_reason  TEXT
);
CREATE INDEX IF NOT EXISTS idx_holds_live     ON holds (listing_id, state, expires_at);
CREATE INDEX IF NOT EXISTS idx_holds_organiser ON holds (organiser_id, state);
CREATE INDEX IF NOT EXISTS idx_holds_supplier  ON holds (supplier_id, state);

CREATE TABLE IF NOT EXISTS hold_events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    hold_id    TEXT NOT NULL REFERENCES holds(id),
    event_type TEXT NOT NULL,
    from_state TEXT,
    to_state   TEXT,
    actor      TEXT,
    at         TEXT NOT NULL
);
"""


class HoldStore:
    """SQLite-backed binding-reserve store. One instance == one DB file.

    All write paths take the whole-DB write lock via ``BEGIN IMMEDIATE`` (single writer),
    so the guarded decrement is atomic against concurrent place-holds. ``now`` is
    injectable on every method for deterministic tests.
    """

    def __init__(self, db_path: str | Path = "marketplace.db"):
        self.db_path = str(db_path)
        self._lock = threading.RLock()  # serialize the shared connection (see _synchronized)
        # autocommit (isolation_level=None) so WE own BEGIN IMMEDIATE / COMMIT explicitly
        # (pitfall 2: a bare/deferred BEGIN throws SQLITE_BUSY even with busy_timeout).
        self._conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")     # readers don't block the writer
        self._conn.execute("PRAGMA busy_timeout = 5000")    # wait for the write lock, don't error
        self._conn.execute("PRAGMA foreign_keys = ON")      # off by default in SQLite!
        self._conn.execute("PRAGMA synchronous = NORMAL")   # safe with WAL
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Internal txn helpers
    # ------------------------------------------------------------------ #
    def _begin(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def _event(self, hold_id: str, kind: str, frm: str | None, to: str | None, actor: str, at: str) -> None:
        self._conn.execute(
            "INSERT INTO hold_events (hold_id, event_type, from_state, to_state, actor, at) "
            "VALUES (?,?,?,?,?,?)",
            (hold_id, kind, frm, to, actor, at),
        )

    def _reclaim_expired(self, listing_id: str, now_iso: str) -> None:
        """Release any expired ``requested`` holds on this listing back into the pool, in
        the current txn (reclaim-on-place — research §7a-i). Idempotent: the
        ``WHERE state='requested'`` guard means a hold is reclaimed at most once.
        """
        expired = self._conn.execute(
            "SELECT id, qty FROM holds "
            "WHERE listing_id = ? AND state = 'requested' AND expires_at <= ?",
            (listing_id, now_iso),
        ).fetchall()
        if not expired:
            return
        returned = sum(float(r["qty"]) for r in expired)
        self._conn.execute(
            "UPDATE listing_inventory SET available_units = available_units + ?, "
            "version = version + 1 WHERE listing_id = ?",
            (returned, listing_id),
        )
        self._conn.execute(
            "UPDATE holds SET state = 'expired', released_at = ?, release_reason = 'expired' "
            "WHERE listing_id = ? AND state = 'requested' AND expires_at <= ?",
            (now_iso, listing_id, now_iso),
        )
        for r in expired:
            self._event(r["id"], "expired", "requested", "expired", "system", now_iso)

    # ------------------------------------------------------------------ #
    # Listing pool registration (the marketplace seeds these from inventory snapshots)
    # ------------------------------------------------------------------ #
    @_synchronized
    def register_listing(
        self,
        listing_id: str,
        *,
        total_units: float,
        material_id: str = "",
        supplier_id: str = "",
        unit: str = "",
        source_url: str = "",
    ) -> None:
        """Register (or no-op if present) the available pool for a listing.

        ``total_units`` is the bindable quantity (kg / m2 / m3 / count). For a scraped
        listing with UNKNOWN quantity the marketplace seeds ``total_units = 1`` and holds
        reserve the whole listing (an exclusive binary lock) — honest: an unknown pool is
        not silently treated as infinite. Re-registering an existing listing is a no-op
        on the pool (it never wipes live holds).
        """
        if total_units < 0:
            raise HoldError(f"total_units must be >= 0, got {total_units}")
        self._begin()
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO listing_inventory "
                "(listing_id, material_id, supplier_id, unit, source_url, total_units, available_units) "
                "VALUES (?,?,?,?,?,?,?)",
                (listing_id, material_id, supplier_id, unit, source_url, total_units, total_units),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------ #
    # Phase 1 — place hold (the atomic core)
    # ------------------------------------------------------------------ #
    @_synchronized
    def place_hold(
        self,
        *,
        listing_id: str,
        organiser_id: str,
        qty: float,
        idempotency_key: str,
        ttl_seconds: int = REQUEST_TTL_S,
        supplier_id: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        """Place a binding hold. Atomic guarded decrement — no double-booking.

        Returns the hold dict (with ``replayed: True`` on an idempotent replay). Raises
        ``InsufficientStock`` (409) if the guard refuses, ``UnknownListing`` if the pool
        was never registered, or ``IdempotencyConflict`` if the key is reused with
        different params.
        """
        if qty <= 0:
            raise HoldError(f"qty must be > 0, got {qty}")
        now_dt = now or _utcnow()
        now_iso = _iso(now_dt)
        expires_iso = _iso(now_dt + timedelta(seconds=ttl_seconds))
        self._begin()
        try:
            # (1) IDEMPOTENCY — replay returns the original hold, never a second decrement.
            existing = self._conn.execute(
                "SELECT * FROM holds WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                if existing["listing_id"] != listing_id or float(existing["qty"]) != float(qty):
                    self._conn.execute("ROLLBACK")
                    raise IdempotencyConflict(
                        f"key {idempotency_key!r} reused with different (listing_id, qty)"
                    )
                self._conn.execute("ROLLBACK")  # no mutation — pure replay
                return self._hydrate(existing, now_dt, replayed=True)

            # (2) confirm the pool exists.
            pool = self._conn.execute(
                "SELECT material_id, supplier_id, unit FROM listing_inventory WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
            if pool is None:
                self._conn.execute("ROLLBACK")
                raise UnknownListing(listing_id)

            # (3) reclaim expired holds on this listing, THEN the guarded decrement.
            self._reclaim_expired(listing_id, now_iso)
            cur = self._conn.execute(
                "UPDATE listing_inventory SET available_units = available_units - ?, "
                "version = version + 1 WHERE listing_id = ? AND available_units >= ?",
                (qty, listing_id, qty),
            )
            if cur.rowcount == 0:
                avail = self._conn.execute(
                    "SELECT available_units FROM listing_inventory WHERE listing_id = ?",
                    (listing_id,),
                ).fetchone()
                self._conn.execute("ROLLBACK")
                raise InsufficientStock(listing_id, qty, float(avail["available_units"]) if avail else 0.0)

            # (4) create the BINDING hold + (5) audit event.
            hold_id = uuid4().hex
            sup = supplier_id if supplier_id is not None else pool["supplier_id"]
            self._conn.execute(
                "INSERT INTO holds (id, listing_id, material_id, organiser_id, supplier_id, qty, "
                "unit, state, idempotency_key, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?, 'requested', ?,?,?)",
                (hold_id, listing_id, pool["material_id"], organiser_id, sup, qty,
                 pool["unit"], idempotency_key, now_iso, expires_iso),
            )
            self._event(hold_id, "hold_placed", None, "requested", f"organiser:{organiser_id}", now_iso)
            self._conn.execute("COMMIT")
        except Exception:
            # ROLLBACK already issued on the handled rejections; this guards the rest.
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        return self.get_hold(hold_id, now=now_dt)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Phase 2 — supplier confirm (guarded state flip, NO inventory change)
    # ------------------------------------------------------------------ #
    @_synchronized
    def confirm_hold(self, hold_id: str, *, supplier_id: str | None = None, now: datetime | None = None) -> dict:
        """requested -> confirmed, only if still alive (not expired). Extends the deadline
        to the collection window. Inventory is NOT touched (decrement happened at hold
        time — pitfall 8). Raises ``IllegalTransition`` if expired/already actioned.
        """
        now_dt = now or _utcnow()
        now_iso = _iso(now_dt)
        collect_iso = _iso(now_dt + timedelta(seconds=COLLECT_TTL_S))
        self._begin()
        try:
            self._reclaim_expired_for_hold(hold_id, now_iso)
            params = [now_iso, collect_iso, hold_id, now_iso]
            sql = (
                "UPDATE holds SET state = 'confirmed', confirmed_at = ?, expires_at = ? "
                "WHERE id = ? AND state = 'requested' AND expires_at > ?"
            )
            if supplier_id is not None:
                sql += " AND supplier_id = ?"
                params.append(supplier_id)
            cur = self._conn.execute(sql, params)
            if cur.rowcount == 0:
                self._fail_transition(hold_id, "requested")
            self._event(hold_id, "supplier_confirmed", "requested", "confirmed",
                        f"supplier:{supplier_id or ''}", now_iso)
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        return self.get_hold(hold_id, now=now_dt)  # type: ignore[return-value]

    @_synchronized
    def decline_hold(self, hold_id: str, *, supplier_id: str | None = None, now: datetime | None = None) -> dict:
        """Supplier declines a requested hold -> released, units returned to the pool."""
        return self._release(hold_id, reason="declined", from_states=("requested",),
                             actor=f"supplier:{supplier_id or ''}", now=now)

    @_synchronized
    def cancel_hold(self, hold_id: str, *, organiser_id: str | None = None, now: datetime | None = None) -> dict:
        """Organiser cancels a requested OR confirmed hold -> released, units returned."""
        return self._release(hold_id, reason="cancelled", from_states=("requested", "confirmed"),
                             actor=f"organiser:{organiser_id or ''}", now=now)

    @_synchronized
    def collect_hold(self, hold_id: str, *, now: datetime | None = None) -> dict:
        """confirmed -> collected (terminal). Units are NOT returned (physically gone)."""
        now_dt = now or _utcnow()
        now_iso = _iso(now_dt)
        self._begin()
        try:
            cur = self._conn.execute(
                "UPDATE holds SET state = 'collected' WHERE id = ? AND state = 'confirmed'",
                (hold_id,),
            )
            if cur.rowcount == 0:
                self._fail_transition(hold_id, "confirmed")
            self._event(hold_id, "collected", "confirmed", "collected", "system", now_iso)
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        return self.get_hold(hold_id, now=now_dt)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Shared release path (decline / cancel) — returns units, guarded once.
    # ------------------------------------------------------------------ #
    def _release(self, hold_id: str, *, reason: str, from_states: tuple[str, ...],
                 actor: str, now: datetime | None) -> dict:
        now_dt = now or _utcnow()
        now_iso = _iso(now_dt)
        self._begin()
        try:
            row = self._conn.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
            if row is None:
                self._conn.execute("ROLLBACK")
                raise HoldNotFound(hold_id)
            if row["state"] not in from_states:
                self._conn.execute("ROLLBACK")
                raise IllegalTransition(hold_id, "|".join(from_states), row["state"])
            # Return the units (pitfall 9: guard so a double-release can't double-credit).
            self._conn.execute(
                "UPDATE listing_inventory SET available_units = available_units + ?, "
                "version = version + 1 WHERE listing_id = ?",
                (float(row["qty"]), row["listing_id"]),
            )
            self._conn.execute(
                "UPDATE holds SET state = 'released', released_at = ?, release_reason = ? WHERE id = ?",
                (now_iso, reason, hold_id),
            )
            self._event(hold_id, "released", row["state"], "released", actor, now_iso)
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        return self.get_hold(hold_id, now=now_dt)  # type: ignore[return-value]

    def _reclaim_expired_for_hold(self, hold_id: str, now_iso: str) -> None:
        """Reclaim THIS hold if it has expired (used before confirm so a stale requested
        hold can't be confirmed). Cheap: looks up the listing then reclaims it."""
        row = self._conn.execute("SELECT listing_id FROM holds WHERE id = ?", (hold_id,)).fetchone()
        if row is not None:
            self._reclaim_expired(row["listing_id"], now_iso)

    def _fail_transition(self, hold_id: str, want: str) -> None:
        row = self._conn.execute("SELECT state FROM holds WHERE id = ?", (hold_id,)).fetchone()
        self._conn.execute("ROLLBACK")
        if row is None:
            raise HoldNotFound(hold_id)
        raise IllegalTransition(hold_id, want, row["state"])

    # ------------------------------------------------------------------ #
    # Lazy expiry sweep (cosmetic hygiene; correctness already lives in-txn)
    # ------------------------------------------------------------------ #
    @_synchronized
    def expire_due(self, *, listing_id: str | None = None, now: datetime | None = None) -> int:
        """Release all expired ``requested`` holds (optionally one listing). Returns the
        count expired. Optional — reads/place already treat expired holds correctly."""
        now_iso = _iso(now or _utcnow())
        self._begin()
        try:
            if listing_id is not None:
                ids = [listing_id]
            else:
                ids = [r["listing_id"] for r in self._conn.execute(
                    "SELECT DISTINCT listing_id FROM holds WHERE state = 'requested' AND expires_at <= ?",
                    (now_iso,),
                ).fetchall()]
            before = self._conn.execute(
                "SELECT COUNT(*) c FROM holds WHERE state = 'requested' AND expires_at <= ?",
                (now_iso,),
            ).fetchone()["c"]
            for lid in ids:
                self._reclaim_expired(lid, now_iso)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return before

    # ------------------------------------------------------------------ #
    # Reads (lazy-expiry aware — never report an expired requested hold as live)
    # ------------------------------------------------------------------ #
    def _hydrate(self, row: sqlite3.Row, now: datetime, *, replayed: bool = False) -> dict:
        """Row -> API dict, computing the live remaining-seconds against ``now`` and
        treating an expired ``requested`` row as effectively expired (read-time honesty)."""
        d = dict(row)
        state = d["state"]
        exp = _parse(d["expires_at"])
        if state == "requested" and exp <= now:
            state = "expired"  # read-time honesty: deadline passed, not yet swept
        d["state"] = state
        d["live"] = state in _LIVE_STATES
        d["remaining_seconds"] = (
            max(0, int((exp - now).total_seconds())) if state in _LIVE_STATES else 0
        )
        if replayed:
            d["replayed"] = True
        return d

    @_synchronized
    def get_hold(self, hold_id: str, *, now: datetime | None = None) -> dict | None:
        row = self._conn.execute("SELECT * FROM holds WHERE id = ?", (hold_id,)).fetchone()
        return self._hydrate(row, now or _utcnow()) if row is not None else None

    @_synchronized
    def availability(self, listing_id: str, *, now: datetime | None = None) -> dict:
        """Available units for a listing, lazy-expiry corrected (expired requested holds
        counted back into the pool at read time, even before they're swept)."""
        now_iso = _iso(now or _utcnow())
        pool = self._conn.execute(
            "SELECT * FROM listing_inventory WHERE listing_id = ?", (listing_id,)
        ).fetchone()
        if pool is None:
            raise UnknownListing(listing_id)
        reclaimable = self._conn.execute(
            "SELECT COALESCE(SUM(qty),0) s FROM holds "
            "WHERE listing_id = ? AND state = 'requested' AND expires_at <= ?",
            (listing_id, now_iso),
        ).fetchone()["s"]
        return {
            "listing_id": listing_id,
            "total_units": float(pool["total_units"]),
            "available_units": float(pool["available_units"]) + float(reclaimable),
            "unit": pool["unit"],
        }

    @_synchronized
    def list_for_organiser(self, organiser_id: str, *, now: datetime | None = None) -> list[dict]:
        now_dt = now or _utcnow()
        rows = self._conn.execute(
            "SELECT * FROM holds WHERE organiser_id = ? ORDER BY created_at DESC", (organiser_id,)
        ).fetchall()
        return [self._hydrate(r, now_dt) for r in rows]

    @_synchronized
    def list_for_supplier(self, supplier_id: str, *, states: tuple[str, ...] | None = None,
                          now: datetime | None = None) -> list[dict]:
        now_dt = now or _utcnow()
        rows = self._conn.execute(
            "SELECT * FROM holds WHERE supplier_id = ? ORDER BY created_at DESC", (supplier_id,)
        ).fetchall()
        out = [self._hydrate(r, now_dt) for r in rows]
        if states is not None:
            out = [h for h in out if h["state"] in states]
        return out

    @_synchronized
    def listings_for_supplier(self, supplier_id: str, *, now: datetime | None = None) -> list[dict]:
        """A supplier's listing pools with live held/available split (the 'My listings'
        table). ``held_units`` counts only currently-live holds (lazy-expiry corrected)."""
        now_iso = _iso(now or _utcnow())
        rows = self._conn.execute(
            "SELECT * FROM listing_inventory WHERE supplier_id = ? ORDER BY listing_id", (supplier_id,)
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            reclaimable = self._conn.execute(
                "SELECT COALESCE(SUM(qty),0) s FROM holds WHERE listing_id = ? "
                "AND state = 'requested' AND expires_at <= ?",
                (r["listing_id"], now_iso),
            ).fetchone()["s"]
            available = float(r["available_units"]) + float(reclaimable)
            out.append({
                "listing_id": r["listing_id"],
                "material_id": r["material_id"],
                "unit": r["unit"],
                "source_url": r["source_url"],
                "total_units": float(r["total_units"]),
                "available_units": available,
                "held_units": float(r["total_units"]) - available,
            })
        return out

    @_synchronized
    def available_listings_by_material(self, *, now: datetime | None = None) -> dict[str, list[dict]]:
        """Map material_id -> its registered listing pools that still have available stock
        (lazy-expiry corrected). The catalogue uses this so an ONBOARDED supplier's listed
        stock is bindable — not only scrape-seeded listings. Nearest/most-available first.
        """
        now_iso = _iso(now or _utcnow())
        rows = self._conn.execute(
            "SELECT * FROM listing_inventory WHERE material_id != '' ORDER BY listing_id"
        ).fetchall()
        out: dict[str, list[dict]] = {}
        for r in rows:
            reclaimable = self._conn.execute(
                "SELECT COALESCE(SUM(qty),0) s FROM holds WHERE listing_id = ? "
                "AND state = 'requested' AND expires_at <= ?",
                (r["listing_id"], now_iso),
            ).fetchone()["s"]
            available = float(r["available_units"]) + float(reclaimable)
            if available <= 0:
                continue
            out.setdefault(r["material_id"], []).append({
                "listing_id": r["listing_id"],
                "supplier_id": r["supplier_id"],
                "unit": r["unit"],
                "source_url": r["source_url"],
                "available_units": available,
            })
        for mid in out:
            out[mid].sort(key=lambda x: -x["available_units"])
        return out

    @_synchronized
    def events(self, hold_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM hold_events WHERE hold_id = ? ORDER BY seq", (hold_id,)
        ).fetchall()
        return [dict(r) for r in rows]
