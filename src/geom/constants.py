"""The ONE place every Phase-4 PRD/ASSUMED magic number lives (mirrors ``core.constants``).

Every downstream Phase-4 module (``request.ts``, ``sun_vector.ts``, ``decode.py``,
``reference_generator.py``, ``geom.ts``) and every Phase-4 test imports its constants from
here — the numbers are NEVER inlined. Phase 4 is the deterministic Structural Geometry stage:
it assembles a frozen ``gh_request`` from the footprint + flow vectors + sun vector, hands it to
Rhino.Compute/Grasshopper (live) or a recorded fixture / PREVIEW generator (offline), then
decodes the returned ``OUT_Mesh`` to ``.gltf``/``.obj``. It makes NO engineering claim — the
Karamba pre-screening is "live-only, pre-screening, requires engineering sign-off" (GEOM-04);
there is no "certified"/"engineer-approved" vocabulary in this stage.

This module imports nothing heavy (pure floats/ints/tuples) so it loads with NO ``geom`` extra
installed — only the live decode path lazy-imports rhino3dm/trimesh (mirror of ``core.constants``
loading torch-free).

Two provenance tiers are tagged inline (same discipline as ``core.constants`` / ``crowd.constants``):

* ``[CITED: ...]`` — verbatim PRD numbers. Immutable; never tune to pass a test.
* ``[ASSUMED An]`` — Claude's-discretion defaults (CONTEXT.md §Claude's Discretion).
  Documented here; adjustable BEFORE any accepted run, immutable after (acceptance-integrity
  discipline — mirrors the Phase-0 X/Y lock).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW reference-generator geometry  [ASSUMED]  (demo-only, coarse)
# ─────────────────────────────────────────────────────────────────────────────

#: PREVIEW pillar-grid spacing (m). [ASSUMED A4] coarse demo-only grid for the offline
#: reference generator — NOT a structural design value (the live Karamba solve owns real
#: spacing). Named here so it is never an inline literal.
GRID_SPACING_M: float = 12.0

#: Half an egress-lane clearance (m) — grid points within this distance of any flow line are
#: culled so shade never lands on a crowd route. [ASSUMED A2] (RESEARCH GEOM-02).
FLOW_BUFFER_M: float = 4.0

# ─────────────────────────────────────────────────────────────────────────────
# Rhino.Compute endpoint  [CITED]
# ─────────────────────────────────────────────────────────────────────────────

#: Rhino.Compute HTTP port. [CITED: PRD §Phase 4 endpoint :8081/grasshopper].
RHINO_PORT: int = 8081

# ─────────────────────────────────────────────────────────────────────────────
# Sun vector  [ASSUMED]
# ─────────────────────────────────────────────────────────────────────────────

#: Peak-sun hour (local) used to compute the deterministic IN_SunVector. [ASSUMED A1] the
#: midpoint of the climate ``PEAK_HEAT_HOUR_BAND`` (12, 16) — do NOT invent a new band; reuse
#: the climate band's midpoint so the geometry's solar assumption matches the heat grid's.
PEAK_SUN_HOUR: int = 14

#: Parc del Forum site centroid (lat, lon, WGS84). [ASSUMED A3] reuse the Phase-2a fixed-site
#: centroid so the sun-position math anchors to the same venue the climate grid was computed over.
PARC_DEL_FORUM_LATLON: tuple[float, float] = (41.4106, 2.2270)

# ─────────────────────────────────────────────────────────────────────────────
# Decoded-mesh bbox sanity bounds  [ASSUMED]  (Pitfall 12)
# ─────────────────────────────────────────────────────────────────────────────

#: Lower bound (m) on the decoded venue mesh's horizontal bbox span. [ASSUMED A5] the real
#: primavera-demo footprint spans ~588x768 m, so a decoded mesh smaller than this is a units /
#: origin-translation bug (mm-vs-m, un-translated coords). Guards the Wave-3 decode test.
BBOX_MIN_M: float = 50.0

#: Upper bound (m) on the decoded venue mesh's horizontal bbox span. [ASSUMED A5] a mesh larger
#: than this overshot the venue (e.g. left in EPSG absolute coords ~4.5e6). Guards the decode test.
BBOX_MAX_M: float = 2000.0

# ─────────────────────────────────────────────────────────────────────────────
# Provenance label  [ASSUMED]
# ─────────────────────────────────────────────────────────────────────────────

#: PREVIEW/ASSUMED provenance label applied to every byte the reference generator emits, so a
#: PREVIEW artifact is never mistaken for a live Karamba-screened solve. [ASSUMED A4].
PREVIEW_LABEL: str = "PREVIEW"
