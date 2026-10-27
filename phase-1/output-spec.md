# Output Specification — `data/materials.json`

- **Format:** JSON (existing schema_version "2.0"), one `materials[]` array + `_meta`.
- **Distribution:** in-repo at `data/materials.json`; consumed by `src/inventory/classifier.py`, `src/marketplace/catalog.py`, `src/selection/`, served via `GET /api/marketplace/materials`.
- **Refresh cadence:** per-deployment / when a spec source is updated. Versioned via `_meta.schema_version` + a new `_meta.specs_sourced_at`.
- **Licence:** internal project data; cited sources retain their own licences (recorded per field).
- **CRS:** n/a (scalar distance_km, not projected coords).

## Per-archetype schema (with REQUIRED provenance per sourced field)

| Field | Type | Unit | Provenance requirement |
|---|---|---|---|
| `id` | string | — | stable slug |
| `name` | string | — | — |
| `type` | enum STRUCT\|MEMBR | — | — |
| `source` | string | — | atlas operator + town (GROUNDED to atlas) |
| `unit` | enum metre\|m2\|unit | — | — |
| `dimensions.unit_mass_kg` | number | kg/unit | **datasheet/EPD areal-density × thickness, or product spec** |
| `dimensions.thickness_mm` | number | mm | **datasheet** |
| `usage_conditions.max_span_meters` | number | m | **engineering/datasheet or structural rule** |
| `usage_conditions.waterproof` | bool | — | datasheet |
| `cost_per_unit` | number | EUR | **supplier price / reclaim-market rate** |
| `solar_transmissivity` | number\|null | 0–1 | **datasheet shade-factor (1−shade%), or openness ratio; null for opaque structural** |
| `lca_profile.distance_km` | number | km | **road route supplier-town→Fòrum (DERIVED) or atlas (GROUNDED)** |
| `lca_profile.transport_mode_factor` | number | kgCO₂e/t·km | **DEFRA/EPD freight factor (GROUNDED) — replaces the 0.10 placeholder** |

## Provenance ledger (NEW — the core deliverable of this phase)

Add `_meta.field_provenance` (or a sibling `data/materials_provenance.json`) mapping each `(material_id, field)` → `{tier: GROUNDED|DERIVED|DECLARED, source: "<citation/URL>", note}`. **No spec number ships without a tier.** A DECLARED number is allowed only where no real source exists, and it is labelled as such — never passed as fact.

## FAIR posture
- **Findable:** in-repo path + `_meta` version.
- **Accessible:** plain JSON, no auth.
- **Interoperable:** existing schema other modules already read.
- **Reusable:** per-field provenance + source citations make every number auditable.
