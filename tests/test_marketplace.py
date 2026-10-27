"""Marketplace binding-hold store tests (MKT-03 / MKT-06).

Base tier — pure stdlib sqlite, no torch / no network / no marker. Proves the
load-bearing guarantee (a claim BINDS and can never double-book) including a real
multi-connection concurrency race, plus idempotency, the state machine, and lazy expiry.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from marketplace.holds import (
    HoldStore,
    IdempotencyConflict,
    IllegalTransition,
    InsufficientStock,
    UnknownListing,
    _utcnow,
)


@pytest.fixture
def store(tmp_path):
    s = HoldStore(tmp_path / "mk.db")
    yield s
    s.close()


def _reg(store, listing_id="scaffold-01", total=1000.0, **kw):
    store.register_listing(listing_id, total_units=total, material_id="struct-scaffold-tube-48",
                           supplier_id="rebuild-cat", unit="kg", **kw)
    return listing_id


# --------------------------------------------------------------------------- #
# Place hold + the atomic guarded decrement
# --------------------------------------------------------------------------- #
def test_place_hold_decrements_and_binds(store):
    lid = _reg(store, total=1000.0)
    h = store.place_hold(listing_id=lid, organiser_id="primavera", qty=600, idempotency_key="k1")
    assert h["state"] == "requested"
    assert h["live"] is True
    assert h["remaining_seconds"] > 0          # a REAL countdown, not decorative
    assert store.availability(lid)["available_units"] == 400.0


def test_place_hold_on_unknown_listing_raises(store):
    with pytest.raises(UnknownListing):
        store.place_hold(listing_id="nope", organiser_id="x", qty=1, idempotency_key="k")


def test_guard_refuses_oversell(store):
    lid = _reg(store, total=100.0)
    store.place_hold(listing_id=lid, organiser_id="a", qty=80, idempotency_key="ka")
    with pytest.raises(InsufficientStock) as ei:
        store.place_hold(listing_id=lid, organiser_id="b", qty=40, idempotency_key="kb")
    assert ei.value.available == 20.0
    # the failed hold did NOT consume anything (atomic rollback)
    assert store.availability(lid)["available_units"] == 20.0


# --------------------------------------------------------------------------- #
# MKT-06 — real concurrency: N writers race for the last units, no double-book
# --------------------------------------------------------------------------- #
def test_no_double_book_under_concurrency(tmp_path):
    db = tmp_path / "race.db"
    seed = HoldStore(db)
    _reg(seed, listing_id="L", total=10.0)     # exactly 10 single-unit holds can win
    seed.close()

    results: list[bool] = []
    lock = threading.Lock()

    def worker(i: int):
        s = HoldStore(db)                       # its OWN connection to the same file
        try:
            s.place_hold(listing_id="L", organiser_id=f"org{i}", qty=1, idempotency_key=f"key{i}")
            ok = True
        except InsufficientStock:
            ok = False
        finally:
            s.close()
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 10                   # exactly the pool, never 11
    check = HoldStore(db)
    assert check.availability("L")["available_units"] == 0.0
    check.close()


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def test_idempotent_replay_does_not_double_decrement(store):
    lid = _reg(store, total=100.0)
    h1 = store.place_hold(listing_id=lid, organiser_id="a", qty=30, idempotency_key="same")
    h2 = store.place_hold(listing_id=lid, organiser_id="a", qty=30, idempotency_key="same")
    assert h2["replayed"] is True
    assert h1["id"] == h2["id"]
    assert store.availability(lid)["available_units"] == 70.0   # decremented ONCE


def test_idempotency_key_reuse_with_different_params_rejected(store):
    lid = _reg(store, total=100.0)
    store.place_hold(listing_id=lid, organiser_id="a", qty=30, idempotency_key="same")
    with pytest.raises(IdempotencyConflict):
        store.place_hold(listing_id=lid, organiser_id="a", qty=50, idempotency_key="same")


# --------------------------------------------------------------------------- #
# State machine
# --------------------------------------------------------------------------- #
def test_confirm_then_collect_happy_path(store):
    lid = _reg(store, total=100.0)
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=10, idempotency_key="k")
    c = store.confirm_hold(h["id"], supplier_id="rebuild-cat")
    assert c["state"] == "confirmed"
    assert c["confirmed_at"] is not None
    assert store.availability(lid)["available_units"] == 90.0   # confirm does NOT re-decrement
    col = store.collect_hold(h["id"])
    assert col["state"] == "collected"
    assert store.availability(lid)["available_units"] == 90.0   # collected units stay gone


def test_decline_returns_units(store):
    lid = _reg(store, total=100.0)
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=40, idempotency_key="k")
    store.decline_hold(h["id"], supplier_id="rebuild-cat")
    assert store.get_hold(h["id"])["state"] == "released"
    assert store.availability(lid)["available_units"] == 100.0


def test_cancel_confirmed_returns_units(store):
    lid = _reg(store, total=100.0)
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=40, idempotency_key="k")
    store.confirm_hold(h["id"])
    store.cancel_hold(h["id"], organiser_id="a")
    assert store.get_hold(h["id"])["state"] == "released"
    assert store.availability(lid)["available_units"] == 100.0


def test_illegal_transition_collect_unconfirmed(store):
    lid = _reg(store, total=100.0)
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=10, idempotency_key="k")
    with pytest.raises(IllegalTransition):
        store.collect_hold(h["id"])             # can't collect a merely-requested hold


# --------------------------------------------------------------------------- #
# Lazy TTL expiry (no scheduler) — read-time honesty + reclaim-on-place
# --------------------------------------------------------------------------- #
def test_expired_hold_reads_as_expired_and_frees_pool(store):
    lid = _reg(store, total=100.0)
    t0 = _utcnow()
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=60,
                         idempotency_key="k", ttl_seconds=900, now=t0)
    later = t0 + timedelta(seconds=901)
    # read-time honesty: the requested hold is past its deadline -> reads as expired
    assert store.get_hold(h["id"], now=later)["state"] == "expired"
    # availability reclaims it at read time even before a sweep
    assert store.availability(lid, now=later)["available_units"] == 100.0


def test_reclaim_on_place_lets_a_new_hold_take_expired_units(store):
    lid = _reg(store, total=100.0)
    t0 = _utcnow()
    store.place_hold(listing_id=lid, organiser_id="a", qty=100,
                     idempotency_key="ka", ttl_seconds=900, now=t0)   # whole pool held
    later = t0 + timedelta(seconds=901)
    # a fresh hold after expiry succeeds because place reclaims the expired units in-txn
    h2 = store.place_hold(listing_id=lid, organiser_id="b", qty=100,
                          idempotency_key="kb", ttl_seconds=900, now=later)
    assert h2["state"] == "requested"
    assert store.availability(lid, now=later)["available_units"] == 0.0


def test_confirm_after_expiry_is_illegal(store):
    lid = _reg(store, total=100.0)
    t0 = _utcnow()
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=10,
                         idempotency_key="k", ttl_seconds=900, now=t0)
    later = t0 + timedelta(seconds=901)
    with pytest.raises(IllegalTransition):
        store.confirm_hold(h["id"], now=later)   # too late — deadline passed


def test_event_log_records_lifecycle(store):
    lid = _reg(store, total=100.0)
    h = store.place_hold(listing_id=lid, organiser_id="a", qty=10, idempotency_key="k")
    store.confirm_hold(h["id"])
    store.collect_hold(h["id"])
    kinds = [e["event_type"] for e in store.events(h["id"])]
    assert kinds == ["hold_placed", "supplier_confirmed", "collected"]
