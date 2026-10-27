"""Deterministic listing -> frozen-material classifier (D-09, Pitfall 6, MAT-01).

Binds a scraped inventory listing to exactly ONE of the 10 frozen
``data/materials.json`` ids by a pure deterministic rule engine — keyword/regex on
the material class + numeric dimension gates. There is NO model inference, NO vector
similarity, NO fuzzy "best guess" anywhere in this module (CLAUDE.md / PRD §6
agents-never-design; "if the model is removed, which decision changes? None."). An
ambiguous, both-class, no-match, or >1-match listing is **rejected with a structured,
non-empty reason** — never silently dropped, never auto-assigned (05-RESEARCH §Q3;
Pitfall 5 never-silent-drop).

Two-stage design (05-RESEARCH §Q3 "match-then-confirm"):
  Stage A — COARSE CLASS: bilingual ES+EN keyword scan over title+product_type+body.
            BOTH coarse classes present, or NEITHER -> reject("ambiguous coarse class").
  Stage B — SPECIFIC TYPE: per-frozen-material rule (required keyword set + optional
            numeric dimension gate). exactly 1 match -> bind material_id; 0 -> reject;
            >1 -> reject (ambiguous, never pick one).

``classify_batch`` provides the conservation guarantee: ``accepted + rejected`` equals
the number of listings, and every rejection carries a non-empty ``reason``.

karpathy: plain dicts + a static rule table. No model, no scorer, no ranker — the only
"accept" path is an exact single rule match.
"""

from __future__ import annotations

import unicodedata

# --------------------------------------------------------------------------- #
# Stage A — coarse-class keyword sets (bilingual ES + EN). Accent-insensitive.
# A listing carrying keywords from BOTH classes (or NEITHER) is rejected — the
# deterministic, honest outcome (never guess). 05-RESEARCH §Q3 keyword tables.
# --------------------------------------------------------------------------- #
MEMBRANE_KEYWORDS: frozenset[str] = frozenset(
    {
        # EN
        "fabric", "textile", "deadstock", "vinyl", "tarp", "tarpaulin",
        "shrink", "shrinkwrap", "shrink-wrap", "carpet", "membrane", "sheet",
        "shade net", "shade", "net", "billboard",
        # atlas-sourced (2026-06-22): marine sailcloth, PP cargo net, recycled HDPE
        # sheet, recycled shade-cloth.
        "sail", "sailcloth", "dacron", "canvas", "cargo", "mesh", "cloth",
        "hdpe", "polyethylene", "plate",
        # ES
        "lona", "malla", "moqueta", "tela", "sombra", "vinilo",
        "vela", "polietileno",
    }
)

STRUCT_KEYWORDS: frozenset[str] = frozenset(
    {
        # EN
        "scaffold", "truss", "pallet", "fence", "chair", "seat", "tube", "pipe",
        # atlas-sourced (2026-06-22): reclaimed steel I-beam, corten container panel.
        "beam", "i-beam", "ibeam", "rsj", "girder", "steel", "corten", "container",
        # ES
        "andamio", "palet", "valla", "silla", "tubo", "celosia",
        "viga", "acero", "contenedor",
    }
)

# Coarse-class labels.
_MEMBRANE = "MEMBR"
_STRUCT = "STRUCT"


# --------------------------------------------------------------------------- #
# Stage B — per-frozen-material rule table. Each rule binds to ONE materials.json
# id and requires ALL of a keyword set (any one synonym group satisfies a group)
# plus an OPTIONAL numeric dimension gate. The class field keeps Stage B candidates
# inside the Stage A coarse class so a tube can never match a membrane rule.
#
# ``keywords_all`` is a list of synonym GROUPS: every group must be satisfied by at
# least one of its members (so {"shade"|"malla", "net"|"sombra"} requires a
# shade/malla token AND a net/sombra token).
# --------------------------------------------------------------------------- #
_RULES: tuple[dict, ...] = (
    {
        "material_id": "struct-scaffold-tube-48",
        "klass": _STRUCT,
        "keywords_all": [("andamio", "scaffold", "tubo", "tube", "pipe")],
        "dimension_gate": {"kind": "diameter_mm", "values": (48.0, 48.3), "tol": 0.5},
    },
    {
        "material_id": "struct-alu-truss-h30v",
        "klass": _STRUCT,
        "keywords_all": [("truss", "celosia")],
    },
    {
        "material_id": "struct-euro-pallet-epal",
        "klass": _STRUCT,
        "keywords_all": [("pallet", "palet", "epal")],
        "dimension_gate": {"kind": "pallet_mm", "length": 1200.0, "width": 800.0, "tol": 60.0},
    },
    {
        "material_id": "struct-heras-fence-panel",
        "klass": _STRUCT,
        "keywords_all": [("heras", "valla", "fence")],
    },
    {
        "material_id": "struct-stadium-chair",
        "klass": _STRUCT,
        "keywords_all": [("chair", "silla", "seat", "stadium")],
    },
    {
        "material_id": "membr-pvc-billboard-vinyl",
        "klass": _MEMBRANE,
        "keywords_all": [("pvc", "vinyl", "vinilo", "billboard")],
    },
    {
        "material_id": "membr-hdpe-shade-net",
        "klass": _MEMBRANE,
        # shade-net: needs a shade/malla token AND a net/mesh/sombra token. (A bare "hdpe"
        # no longer satisfies BOTH groups — that loophole bound plain "HDPE sheet" here;
        # HDPE sheet now has its own archetype below. 2026-06-22. "mesh"/"netting" added so
        # real shade-mesh listings bind, e.g. "Wind Barrier Mesh 50% Shade".)
        "keywords_all": [("shade", "malla"), ("net", "netting", "mesh", "sombra")],
    },
    {
        "material_id": "membr-recycled-pe-tarp",
        "klass": _MEMBRANE,
        # tarp / tarpaulin / "lona PE" — a tarp/tarpaulin/lona token. (Areal-weight gate
        # removed 2026-06-22: real Shopify feeds expose only a shipping `grams`, not areal
        # density, so the gate was meaningless and dropped genuine 110-420 gsm tarps.)
        "keywords_all": [("tarp", "tarpaulin", "lona")],
    },
    {
        "material_id": "membr-pe-yacht-shrinkwrap",
        "klass": _MEMBRANE,
        # GREENWASH FIX (2026-06-22): a bare "shrink" token bound dressmaking-fabric
        # listings ("shrink-resistant jersey") to a maritime shade material. Now require
        # a MARINE/PE qualifier alongside the shrink token — apparel "shrink" can never
        # bind (it carries no yacht/marine/boat/PE-film context).
        "keywords_all": [
            ("shrink", "shrinkwrap", "shrink-wrap"),
            ("yacht", "marine", "boat", "naval", "pe film", "polyethylene",
             "shrinkwrap", "shrink-wrap"),
        ],
    },
    {
        "material_id": "membr-pp-festival-carpet",
        "klass": _MEMBRANE,
        "keywords_all": [("carpet", "moqueta")],
    },
    # --- atlas-sourced archetypes (2026-06-22; barcelona_materials_atlas.md) --------- #
    {
        "material_id": "struct-reclaimed-steel-ibeam",
        "klass": _STRUCT,
        "keywords_all": [("beam", "i-beam", "ibeam", "rsj", "girder", "viga")],
    },
    {
        "material_id": "struct-corten-container-panel",
        "klass": _STRUCT,
        "keywords_all": [("container", "contenedor", "corten")],
    },
    {
        "material_id": "membr-marine-sailcloth",
        "klass": _MEMBRANE,
        "keywords_all": [("sail", "sailcloth", "dacron", "vela")],
    },
    {
        "material_id": "membr-pp-cargo-net",
        "klass": _MEMBRANE,
        # a cargo/carga token AND a net/mesh token (distinct from the shade-net rule,
        # which needs a shade/malla token).
        "keywords_all": [("cargo", "carga"), ("net", "malla", "mesh", "red")],
    },
    {
        "material_id": "membr-recycled-hdpe-sheet",
        "klass": _MEMBRANE,
        # an HDPE/polyethylene token AND a sheet/panel/plate token (the former shade-net
        # loophole now lands here honestly).
        "keywords_all": [("hdpe", "polyethylene", "polietileno"),
                         ("sheet", "panel", "lamina", "plate")],
    },
    {
        "material_id": "membr-recycled-shade-cloth",
        "klass": _MEMBRANE,
        # a "shade cloth" phrase (distinct from shade-NET, which needs a net/sombra token).
        "keywords_all": [("shade cloth", "shadecloth", "shade-cloth", "shade fabric",
                          "shade canvas")],
    },
)


# --------------------------------------------------------------------------- #
# Text normalization (accent + case insensitive)
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    """Lower-case + strip accents (NFKD) so ES diacritics match plain ASCII keywords."""
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower()


def _listing_text(listing: dict) -> str:
    """Concatenate the searchable fields of a listing into one normalized blob.

    Covers both the classifier-sample shape (``raw_title``/``body``) and the adapter
    shape (``raw_title``/``product_type``/``body``) — every text field a deterministic
    keyword scan reads.
    """
    parts = [
        listing.get("raw_title", ""),
        listing.get("title", ""),
        listing.get("product_type", ""),
        listing.get("body", ""),
        listing.get("body_html", ""),
    ]
    return _normalize(" ".join(str(p) for p in parts if p))


def _has_keyword(blob: str, keywords) -> bool:
    """True iff any keyword (already lower/ascii) appears in the normalized blob."""
    return any(_normalize(kw) in blob for kw in keywords)


# --------------------------------------------------------------------------- #
# Dimension gates (numeric tie-breakers; parse-then-bracket, never guess)
# --------------------------------------------------------------------------- #
def _safe_float_dim(v) -> float | None:
    """Parse an untrusted scraped dimension/areal-weight value to float.

    Returns None on any parse failure (MA-02): a non-numeric value (e.g. "~48mm",
    "N/A") is treated as ABSENT — the gate is "not contradicted" — never a ValueError
    that would escape the stage's InventoryFetchError degrade handler and crash the run.
    """
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dimension_gate_ok(gate: dict, listing: dict) -> bool:
    """Evaluate a numeric dimension gate against a listing.

    A gate is SATISFIED iff the listing carries the relevant dimension AND it falls
    inside the bracket. If the listing does NOT carry the dimension at all, the gate is
    treated as "not contradicted" (True) — keyword evidence then carries the bind; a
    PRESENT-but-out-of-bracket dimension fails the gate (e.g. a 60 mm tube is rejected).
    """
    kind = gate["kind"]
    dims = listing.get("dimensions_mm") or {}

    if kind == "diameter_mm":
        dia = _safe_float_dim(dims.get("diameter"))
        if dia is None:
            return True  # no (parseable) diameter quoted -> not contradicted
        return any(abs(dia - v) <= gate["tol"] for v in gate["values"])

    if kind == "pallet_mm":
        length = _safe_float_dim(dims.get("length"))
        width = _safe_float_dim(dims.get("width"))
        if length is None and width is None:
            return True
        tol = gate["tol"]
        len_ok = length is None or abs(length - gate["length"]) <= tol
        wid_ok = width is None or abs(width - gate["width"]) <= tol
        return len_ok and wid_ok

    if kind == "areal_weight_g_m2":
        weight = _safe_float_dim(listing.get("areal_weight_g_m2"))
        if weight is None:
            return True
        return abs(weight - gate["value"]) <= gate["tol"]

    # Unknown gate kind -> do not block on it (deterministic, fail-open on keywords).
    return True


def _coarse_class(blob: str) -> str | dict:
    """Stage A: return _MEMBRANE/_STRUCT, or a rejection dict if ambiguous/none."""
    is_membrane = _has_keyword(blob, MEMBRANE_KEYWORDS)
    is_struct = _has_keyword(blob, STRUCT_KEYWORDS)
    if is_membrane and is_struct:
        return {"status": "rejected", "reason": "ambiguous coarse class"}
    if not is_membrane and not is_struct:
        return {"status": "rejected", "reason": "no resolvable coarse class"}
    return _MEMBRANE if is_membrane else _STRUCT


def _rule_matches(rule: dict, blob: str, listing: dict) -> bool:
    """True iff EVERY keyword group is satisfied AND the dimension gate (if any) holds."""
    for group in rule["keywords_all"]:
        if not _has_keyword(blob, group):
            return False
    gate = rule.get("dimension_gate")
    if gate is not None and not _dimension_gate_ok(gate, listing):
        return False
    return True


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def classify(listing: dict) -> dict:
    """Bind a listing to one frozen material id, or reject it with a reason.

    Args:
        listing: a raw listing dict. Reads ``raw_title``/``title``/``product_type``/
            ``body``/``body_html`` for keywords and ``dimensions_mm`` /
            ``areal_weight_g_m2`` for the numeric gates.

    Returns:
        ``{"material_id": <one of the 10 frozen ids>}`` on a clean single match, or
        ``{"status": "rejected", "reason": <non-empty>}`` for a both-class, no-match,
        or >1-match listing. NEVER a model-inferred / fuzzy "best guess".
    """
    blob = _listing_text(listing)

    coarse = _coarse_class(blob)
    if isinstance(coarse, dict):  # Stage A rejection
        return coarse

    candidates = [r for r in _RULES if r["klass"] == coarse]
    matches = [r["material_id"] for r in candidates if _rule_matches(r, blob, listing)]

    if len(matches) == 1:
        return {"material_id": matches[0]}
    if len(matches) == 0:
        return {"status": "rejected", "reason": "no frozen type matched"}
    return {"status": "rejected", "reason": "listing matched >1 frozen type"}


def classify_batch(listings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Classify many listings, preserving the never-silent-drop conservation guarantee.

    Returns ``(accepted, rejected)`` where ``len(accepted) + len(rejected) ==
    len(listings)`` and every rejection record carries a non-empty ``reason`` plus the
    ``raw_title`` (so the snapshot's required ``rejected[]`` shape is satisfiable).
    Nothing vanishes — the inventory-stage analogue of the Phase-3 infeasibility report.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    for listing in listings:
        result = classify(listing)
        if result.get("status") == "rejected":
            rejected.append(
                {
                    "reason": result["reason"],
                    "raw_title": str(listing.get("raw_title") or listing.get("title") or ""),
                    "source_url": listing.get("source_url", ""),
                }
            )
        else:
            # Carry the bound id + the originating listing for the stage to enrich.
            accepted.append({"material_id": result["material_id"], "listing": listing})
    return accepted, rejected
