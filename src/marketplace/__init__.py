"""Binding-reserve marketplace (Phase B / MKT-03, MKT-06).

The stateful half of the Material Recovery Inventory: turns a browsable scraped listing
into a claim that BINDS. The harvest half (``src/inventory/``) is read-only discovery;
this package owns holds — the real, time-boxed, supplier-confirmable reservations that
remove stock from the available pool atomically (no double-booking).
"""
