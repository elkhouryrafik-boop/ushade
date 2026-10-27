"""Material Recovery Inventory package (Phase 5, D-05..D-10).

Real cache-first scrape adapters over verified live sources, a deterministic
listing -> frozen-material classifier, supplier -> Parc del Fòrum ROAD routing, and a
``run_inventory_stage`` orchestrator that emits a contract-valid ``inventory_snapshot``
per source. Clones the climate network-seam discipline (lazy fetch import, typed error,
live-fetch budget, labelled-never-silent degrade). NO mock data (Pitfall 8). NO LLM in
the classifier (D-09 / agents-never-design). NO logged secret anywhere.
"""

from __future__ import annotations

from inventory.adapters import (
    LIVE_FETCH_CAP,
    ExoandamiajesAdapter,
    HttpFetcher,
    InventoryFetchError,
    LiveFetchBudget,
    MascusAdapter,
    ShopifyAdapter,
    adapter_for,
)
from inventory.classifier import classify, classify_batch
from inventory.routing import (
    DERIVED,
    GROUNDED,
    ROAD_CIRCUITY_FACTOR,
    great_circle_km,
    road_distance_km,
    road_route,
)

__all__ = [
    # adapters
    "LIVE_FETCH_CAP",
    "InventoryFetchError",
    "LiveFetchBudget",
    "HttpFetcher",
    "ShopifyAdapter",
    "ExoandamiajesAdapter",
    "MascusAdapter",
    "adapter_for",
    # classifier
    "classify",
    "classify_batch",
    # routing
    "DERIVED",
    "GROUNDED",
    "ROAD_CIRCUITY_FACTOR",
    "great_circle_km",
    "road_distance_km",
    "road_route",
]
