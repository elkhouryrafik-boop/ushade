"""The Phase-5 selection core — ``select_material`` (pure) + ``run_selection_stage`` (cache-first).

Pipeline (D-01 + D-06, MAT-01/02/06):

  1. soft-filter the frozen 10 by the parsed theme (intersection; zero matches -> fall back to
     ALL membranes, NEVER crash) — MAT-01.
  2. drop tau=null structural materials (a structural-only material can NEVER be the membrane)
     — MAT-06 / D-01.
  3. AVAILABILITY GATE: drop candidates the inventory marks out_of_stock. Availability is a
     FILTER; it NEVER enters the comparator (Pitfall 3 / D-06).
  4. select the MINIMUM by transport_carbon (index 0 after the sort). The sort key is
     transport_carbon ONLY — price/availability NEVER re-rank. If the global min is
     unavailable, walk to the next-lowest-carbon AVAILABLE. If NONE available -> ``infeasible``.

tau touches the cooling correction ONLY (``cooling.py``); cost + carbon are byte-identical
across tau (``carbon.py``). The emitted dict validates against ``material_selection`` 1.1.0 with
``selection_basis == "transport_carbon_min"`` (the honesty marker recording the sort key).

karpathy: ``select_material`` is a pure comparator the tests drive directly; ``run_selection_stage``
clones the climate cache-first / validate-then-write / fail-safe seam for the wired stage.
"""

from __future__ import annotations

import json
from pathlib import Path

# pythonpath=["src","."] (pyproject) makes the sibling packages importable bare.
from manifest.manifest import Manifest, content_hash
from provenance.ledger import ProvenanceLedger
from validate.validate import validate

from selection import carbon as _carbon
from selection import cooling as _cooling
from selection import reporting as _reporting

# Re-export the (1 - tau) cooling correction so tests/callers can import it from the stage
# module alongside ``select_material`` (the test-required public surface). tau enters ONLY
# via ``cooling.py`` — this is a re-export, not a second tau site.
from selection.cooling import cooling_estimate  # noqa: E402,F401

_STAGE = "material_selection"
_CONTRACT = "material_selection"
_SCHEMA_VERSION = "1.1.0"
_ARTIFACT_NAME = "material_selection.json"
_SELECTION_BASIS = "transport_carbon_min"  # the honesty marker: the sort key is NEVER price.

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MATERIALS_PATH = _REPO_ROOT / "data" / "materials.json"

# ASSUMED per-connection fixing mass (A4, D-12). Labelled ASSUMED; feeds fixings_kg_new.
FIXING_MASS_KG_ASSUMED = 2.0

# Availability values that GATE a candidate OUT (D-06). "unknown" + "available" stay IN — an
# unknown stock is never treated as out_of_stock (Pitfall 5: never-silent degrade to false).
_UNAVAILABLE = {"out_of_stock"}


# --------------------------------------------------------------------------- #
# Frozen DB loader (MAT-06)
# --------------------------------------------------------------------------- #
def load_materials() -> list[dict]:
    """Return the frozen 10 from ``data/materials.json`` (MAT-06: exactly 5 struct + 5 membr)."""
    return json.loads(_MATERIALS_PATH.read_text(encoding="utf-8"))["materials"]


# --------------------------------------------------------------------------- #
# Per-candidate transport carbon (the SORT KEY — transport_carbon ONLY, never price)
# --------------------------------------------------------------------------- #
def _candidate_carbon(material: dict, *, qty: float, distance_km: float | None) -> float:
    """Transport carbon for one candidate using the DERIVED inventory road km when present,
    else the frozen ``lca_profile.distance_km`` (GROUNDED fallback). tau never enters here."""
    lca = material["lca_profile"]
    dist = distance_km if distance_km is not None else lca["distance_km"]
    return _carbon.transport_carbon(
        qty, material["dimensions"]["unit_mass_kg"], dist, lca["transport_mode_factor"]
    )


def _theme_filter(candidates: list[dict], theme: str | None) -> list[dict]:
    """Soft-filter by parsed theme (MAT-01). A material carries several themes; keep any match.
    SOFT: zero theme-matches -> return the input unchanged (fall back to all), never crash."""
    if not theme:
        return list(candidates)
    matched = [m for m in candidates if theme in m.get("theme", [])]
    return matched if matched else list(candidates)


def _is_available(material_id: str, availability: dict | None) -> bool:
    """A candidate is gated OUT only when the inventory EXPLICITLY marks it out_of_stock.
    No availability map / unknown -> kept IN (never silently treated as out_of_stock)."""
    if not availability:
        return True
    return availability.get(material_id) not in _UNAVAILABLE


# --------------------------------------------------------------------------- #
# The pure comparator (MAT-01/02/06, D-06) — the tests drive this directly
# --------------------------------------------------------------------------- #
def select_material(
    candidates: list[dict],
    *,
    theme: str | None = None,
    availability: dict | None = None,
    quantity: float = 1.0,
    geometric_cooling: float | None = None,
    distance_overrides: dict | None = None,
    bom: dict | None = None,
    pillar_count: int = 0,
) -> dict:
    """Select the minimum-transport-carbon AVAILABLE membrane and assemble the 1.1.0 dict.

    Args:
        candidates: membrane material dicts (the caller passes the MEMBR slice of the frozen 10).
        theme: parsed brief theme; soft-filters the candidates (MAT-01).
        availability: optional ``{material_id: "available"|"unknown"|"out_of_stock"}`` map — a
            FILTER, never a re-rank key (D-06, Pitfall 3).
        quantity: units of the selected membrane (m²) for cost + carbon roll-up.
        geometric_cooling: optional geometric cooling estimate to scale by (1 - tau) (MAT-04).
        distance_overrides: optional ``{material_id: DERIVED road km}`` from the inventory (Q2);
            absent -> the frozen ``distance_km`` (GROUNDED fallback).
        bom: optional Phase-4 OUT_BOM (``scaffold``/``pillars``) for the mass-balance.
        pillar_count: pillar count for ``fixings_kg_new`` (else taken from ``bom``).

    Returns:
        A ``material_selection`` 1.1.0-shaped dict (``selection_basis == "transport_carbon_min"``).
        If no candidate is available, ``infeasible: True`` with the infeasibility fields.
    """
    distance_overrides = distance_overrides or {}

    # 1) theme soft-filter; 2) drop tau=null structural (can never be the membrane).
    themed = _theme_filter(candidates, theme)
    membranes = [m for m in themed if m.get("solar_transmissivity") is not None]

    candidates_considered = len(membranes)

    def carbon_of(m: dict) -> float:
        return _candidate_carbon(
            m, qty=quantity, distance_km=distance_overrides.get(m["id"])
        )

    # 4) SORT KEY = transport_carbon ONLY (price/availability NEVER re-rank — Pitfall 3).
    by_carbon = sorted(membranes, key=carbon_of)

    # 3) AVAILABILITY GATE walked AFTER the carbon sort: the first AVAILABLE in carbon order is
    #    the lowest-carbon available — not the cheapest, not the global min if it is unavailable.
    selected = next((m for m in by_carbon if _is_available(m["id"], availability)), None)

    gated = availability is not None

    if selected is None:
        # D-06 fallback ladder exhausted: NONE available -> infeasibility report (never an
        # unavailable pick). Mirrors the Phase-3 core infeasibility shape.
        return {
            "schema_version": _SCHEMA_VERSION,
            # Non-empty sentinel: satisfies the contract's minLength:1 (so the infeasibility
            # report VALIDATES + persists honestly) while never colliding with a real frozen
            # material id (those are lower-case slugs). The honest infeasible marker is the
            # required ``infeasible: True`` field below — the artifact is written, NEVER
            # swallowed by the fail-safe (BL-01).
            "selected_id": "INFEASIBLE",
            "is_membrane": False,
            "transport_carbon_kgco2e": 0.0,
            "cost_total_eur": 0.0,
            "solar_transmissivity": None,
            "selection_basis": _SELECTION_BASIS,
            "availability_gated": gated,
            "candidates_considered": candidates_considered,
            "infeasible": True,
        }

    tau = selected["solar_transmissivity"]
    transport_carbon_kgco2e = carbon_of(selected)
    cost_total_eur = _carbon.cost_rollup(quantity, selected["cost_per_unit"])
    correction = _cooling.cooling_correction_factor(tau)

    # Recovery reporting (D-12, D-14, D-13). Scaffold mass from the BOM × unit_mass when present.
    scaffold_units = float((bom or {}).get("scaffold", 0.0) or 0.0)
    pillars = int(pillar_count or (bom or {}).get("pillars", 0) or 0)
    unit_mass = selected["dimensions"]["unit_mass_kg"]
    mass_balance = _reporting.mass_balance(
        scaffold_kg_rented=scaffold_units * unit_mass,
        membrane_m2_recovered=quantity,
        fixings_kg_new=pillars * FIXING_MASS_KG_ASSUMED,
    )

    selection: dict = {
        "schema_version": _SCHEMA_VERSION,
        "selected_id": selected["id"],
        "is_membrane": True,
        "transport_carbon_kgco2e": transport_carbon_kgco2e,
        "cost_total_eur": cost_total_eur,
        "solar_transmissivity": tau,
        "selection_basis": _SELECTION_BASIS,
        "availability_gated": gated,
        "candidates_considered": candidates_considered,
        "cooling_correction_factor": correction,
        "mass_balance": mass_balance,
        "next_life": _reporting.next_life(quantity, unit_mass),
        "tent_comparison": _carbon.tent_comparison(),
        "infeasible": False,
    }

    # The (1 - tau) cooling estimate is attached to the RETURNED dict only when a geometric
    # cooling baseline is supplied (it feeds Phase 5b; it is NOT a contract field).
    if geometric_cooling is not None:
        selection["_cooling_estimate"] = _cooling.cooling_estimate(geometric_cooling, tau)

    return selection


# --------------------------------------------------------------------------- #
# Manifest persistence (mirror run_climate_stage)
# --------------------------------------------------------------------------- #
def _load_manifest(project_id: str, project_root: Path) -> Manifest:
    """Load a persisted manifest if present, else a fresh one (mirror climate)."""
    m = Manifest(project_id, project_root)
    manifest_path = m.project_dir / "manifest.json"
    if not manifest_path.exists():
        return m
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return m
    if "created_at" in data:
        m.created_at = data["created_at"]
    for st in data.get("stages", []):
        name = st.get("name")
        if name in m._stages:
            m._stages[name].update(st)
    return m


def _availability_from_inventory(inventory) -> dict:
    """Merge inventory_snapshot listings into a ``{material_id: availability}`` gate map.

    Accepts a single snapshot dict, a list of snapshots, or an already-merged map. The most
    optimistic availability across sources wins (available > unknown > out_of_stock) — a
    material in stock at ANY source is available; only ALL-sources-out_of_stock gates it out.
    """
    if inventory is None:
        return {}
    if isinstance(inventory, dict) and "listings" not in inventory:
        # already a merged {material_id: availability} map
        return dict(inventory)
    snapshots = inventory if isinstance(inventory, list) else [inventory]
    rank = {"available": 2, "unknown": 1, "out_of_stock": 0}
    merged: dict[str, str] = {}
    for snap in snapshots:
        for listing in (snap or {}).get("listings", []):
            mid = listing.get("material_id")
            avail = listing.get("availability", "unknown")
            if mid is None:
                continue
            if mid not in merged or rank.get(avail, 1) > rank.get(merged[mid], 1):
                merged[mid] = avail
    return merged


def _distances_from_inventory(inventory) -> dict:
    """Pull DERIVED road ``distance_km`` per material from inventory listings (Q2)."""
    if inventory is None or (isinstance(inventory, dict) and "listings" not in inventory):
        return {}
    snapshots = inventory if isinstance(inventory, list) else [inventory]
    distances: dict[str, float] = {}
    for snap in snapshots:
        for listing in (snap or {}).get("listings", []):
            mid = listing.get("material_id")
            dist = listing.get("distance_km")
            if mid is not None and dist is not None and mid not in distances:
                distances[mid] = dist
    return distances


# --------------------------------------------------------------------------- #
# Live wiring (Plan 04): real inventory -> selection composition
# --------------------------------------------------------------------------- #
# The default live source set: the two confirmed Shopify textile sources + the
# Exoandamiajes scaffold source (05-RESEARCH §Q1). Nona Source is intentionally omitted
# (login-walled / unverified) and stays behind a feature flag. This is the LIVE path only
# — the offline tests still inject a fixture snapshot via run_selection_stage's `inventory`
# arg, which is left UNCHANGED so the offline suite stays network-free.
_DEFAULT_LIVE_SOURCES = ("thefabricsales", "fabricsight", "exoandamiajes")

_GH_META_NAME = "gh_meta.json"


def _bom_from_gh_meta(project_id: str, project_root: Path) -> dict:
    """Read the Phase-4 OUT_BOM (``gh_meta.json``) for the mass-balance inputs.

    Returns a BOM dict carrying ``membrane_m2``, ``pillars``, and ``scaffold`` (unit count)
    for ``run_selection_stage``. A missing/partial gh_meta degrades to an empty BOM (the
    selection then falls back to quantity=1.0) — never a fabricated mass.
    """
    meta_path = project_root / project_id / _GH_META_NAME
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_bom = meta.get("bom", {}) or {}
    bom: dict = {}
    if "membrane_m2" in raw_bom:
        bom["membrane_m2"] = raw_bom["membrane_m2"]
    if "pillars" in raw_bom:
        bom["pillars"] = raw_bom["pillars"]
    # scaffold UNIT count for mass_balance (scaffold_kg_rented = units x unit_mass_kg).
    if "scaffold" in raw_bom:
        bom["scaffold"] = raw_bom["scaffold"]
    return bom


def select_from_live_inventory(
    project_id: str,
    parsed_brief: dict,
    *,
    sources=_DEFAULT_LIVE_SOURCES,
    projects_root: Path | str | None = None,
    geometric_cooling: float | None = None,
) -> dict:
    """LIVE composition (Plan 04): fetch the REAL inventory per source, merge the snapshots
    into one availability map, read the Phase-4 OUT_BOM, then run the selection stage.

    This is the ONLY function that reaches the network (via ``run_inventory_stage`` with
    ``fetcher=None`` — the production adapter path). It keeps ``run_selection_stage``'s
    fixture-injectable ``inventory`` arg UNTOUCHED, so the Plan-03 offline selection tests
    stay network-free. An unreachable source degrades to a LABELLED ``stale_snapshot`` /
    ``unavailable`` snapshot (handled inside ``run_inventory_stage``) — NEVER synthetic data
    (Pitfall 8).

    Args:
        project_id: the run id; artifacts live under ``<projects_root>/<project_id>/``.
        parsed_brief: the parsed brief (its ``theme`` soft-filters the candidates).
        sources: the live source ids to fetch (default: the confirmed live set).
        projects_root: where ``<project_id>/`` lives (default ``projects/``).
        geometric_cooling: optional geometric cooling baseline to scale by (1 - tau).

    Returns:
        The ``material_selection`` 1.1.0 dict (also written to disk by the wrapped stage).
    """
    # Lazy import: the live inventory stage pulls in the scrape adapters only when the LIVE
    # path is actually taken — the offline selection tests never import it.
    from inventory.inventory import run_inventory_stage  # noqa: PLC0415

    project_root = Path(projects_root) if projects_root is not None else Path("projects")

    snapshots: list[dict] = []
    for source_id in sources:
        snapshot = run_inventory_stage(
            source_id,
            project_id=project_id,
            fetcher=None,  # production path: real adapter, key from env (never a literal)
            projects_root=project_root,
        )
        snapshots.append(snapshot)

    bom = _bom_from_gh_meta(project_id, project_root)

    return run_selection_stage(
        project_id,
        parsed_brief,
        inventory=snapshots,  # the REAL merged availability map feeds the gate (MAT-02)
        bom=bom or None,
        projects_root=project_root,
        geometric_cooling=geometric_cooling,
    )


# --------------------------------------------------------------------------- #
# The wired stage (cache-first, validate-then-write, fail-safe)
# --------------------------------------------------------------------------- #
def run_selection_stage(
    project_id: str,
    parsed_brief: dict,
    inventory=None,
    bom: dict | None = None,
    *,
    projects_root: Path | str | None = None,
    geometric_cooling: float | None = None,
    quantity: float | None = None,
) -> dict:
    """Run the selection stage: theme filter -> availability gate -> min-carbon ->
    validate-then-write ``material_selection`` 1.1.0 -> ledger. Mirrors ``run_climate_stage``.

    ``inventory`` is a list of ``inventory_snapshot`` dicts (or a merged availability map); the
    test injects a fake snapshot fixture — there is NO Plan-02 runtime import here.
    """
    project_root = Path(projects_root) if projects_root is not None else Path("projects")

    theme = (parsed_brief or {}).get("theme")
    qty = quantity if quantity is not None else float((bom or {}).get("membrane_m2", 1.0) or 1.0)

    input_hash = content_hash(
        {
            "theme": theme,
            "quantity": qty,
            "availability": _availability_from_inventory(inventory),
            "distances": _distances_from_inventory(inventory),
            "bom": bom or {},
        }
    )

    manifest = _load_manifest(project_id, project_root)
    artifact_path = manifest.project_dir / _ARTIFACT_NAME

    # ── 1) CACHE CHECK ────────────────────────────────────────────────────────
    if manifest.is_reusable(_STAGE, input_hash) and artifact_path.exists():
        try:
            cached = json.loads(artifact_path.read_text(encoding="utf-8"))
            validate(cached, _CONTRACT)
            return cached
        except (OSError, json.JSONDecodeError):
            pass  # corrupt cache -> fall through and recompute

    # ── 2) COMPUTE (fail-safe) ────────────────────────────────────────────────
    try:
        membranes = [m for m in load_materials() if m["type"] == "MEMBR"]
        availability = _availability_from_inventory(inventory)
        distances = _distances_from_inventory(inventory)
        selection = select_material(
            membranes,
            theme=theme,
            availability=availability or None,
            quantity=qty,
            geometric_cooling=geometric_cooling,
            distance_overrides=distances,
            bom=bom,
        )

        # The on-disk artifact is the clean contract shape (drop the non-contract _cooling_estimate).
        artifact = {k: v for k, v in selection.items() if not k.startswith("_")}

        # ── 3) VALIDATE-THEN-WRITE ────────────────────────────────────────────
        # Validate against the frozen material_selection 1.1.0 contract BEFORE any byte hits
        # disk (the locked stage discipline) — an invalid/partial selection can never persist.
        validate(artifact, "material_selection")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

        # ── 4) PROVENANCE (carbon ASSUMED, cost + cooling DERIVED, next_life ASSUMED) ──
        ledger = ProvenanceLedger()
        if not artifact.get("infeasible"):
            _carbon.ledger_carbon_entries(
                ledger,
                transport_carbon_kgco2e=artifact["transport_carbon_kgco2e"],
                stage=_STAGE,
                distance_km=distances.get(artifact["selected_id"], 0.0),
            )
            ledger.derived(
                "cost_total_eur",
                artifact["cost_total_eur"],
                "qty x cost_per_unit roll-up into the locked budget (D-02)",
                _STAGE,
                unit="euro",
                formula="quantity * cost_per_unit",
            )
            ledger.derived(
                "cooling_correction_factor",
                artifact["cooling_correction_factor"],
                "(1 - solar_transmissivity), Golden Rule amendment 2026-06-09 (feeds Phase 5b)",
                _STAGE,
                formula="1 - tau",
                inputs=["solar_transmissivity"],
            )
            ledger.assumed(
                "next_life_receiver",
                artifact["next_life"]["receiver"],
                "textile afterlife receiver placeholder (D-14) — flips GROUNDED on a real name",
                _STAGE,
            )
        ledger.write(manifest.project_dir / "selection_ledger.json")

        # mark_done's contract is (name, artifact_path, input_hash, output_hash) — clone the
        # climate-stage call exactly (Rule 3 fix: the Plan-03 keyword-only call hit a
        # TypeError the moment the success/write path ran against the real Manifest).
        output_hash = content_hash(artifact)
        manifest.mark_done(_STAGE, _ARTIFACT_NAME, input_hash, output_hash)
        manifest.write()
        return selection
    except Exception:
        # Fail-safe: leave the stage NOT done, write no partial artifact (mirror climate).
        if hasattr(manifest, "mark_failed"):
            try:
                manifest.mark_failed(_STAGE)
                manifest.write()
            except Exception:
                pass
        raise
