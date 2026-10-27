# Risk Register

| Risk | Likelihood | Impact | Owner | Mitigation | Triggers cancellation? |
|---|---|---|---|---|---|
| No public datasheet exists for a reclaimed-specific material (e.g. "reclaimed marine sailcloth") | H | M | Rafik | Source the virgin-product equivalent datasheet (same physical specs) + label tier DERIVED; only fall back to DECLARED if even that fails | No |
| Datasheet gives a range, not a point (shade factor 60–90%) | H | L | Rafik | Record the range, pick a labelled mid/representative value, cite both | No |
| Category-average mistaken for product spec (e.g. "metals" carbon) | M | H | Rafik | Resolution rule: only accept a spec at material-class granularity; reject category averages | No |
| Atlas-inferred archetype isn't a real reusable product (corten panel, cargo net, sailcloth) | M | H | Rafik | Phase-2 vetting: if no real product/datasheet supports the *use*, drop the archetype rather than fake it | **Yes — if ≥3 of 6 atlas-added archetypes cannot be sourced as real shade-capable products, stop and reframe the catalogue to only atlas-solid materials** |
| Web sources unreachable / paywalled | M | M | Rafik | Use multiple suppliers per class; cite the reachable one; DECLARED fallback labelled | No |
| transport_mode_factor source (DEFRA) not applicable to Spain freight | L | L | Rafik | Use DEFRA road-HGV as a cited proxy, label assumption; note EU EN 16258 alternative | No |
| Provenance ledger drifts from materials.json (number changes, tier not updated) | M | M | Rafik | Single source of truth: a test asserting every spec field has a ledger entry | No |

## Cancellation criterion
**Stop and reframe** if, after Phase-2 data hunting, **≥ 3 of the 6 atlas-added archetypes (steel I-beam, corten container panel, marine sailcloth, PP cargo net, recycled HDPE sheet, recycled shade-cloth) cannot be grounded in a real product datasheet/EPD as a genuinely shade/structure-viable material.** In that case the honest move is to trim the catalogue to atlas-solid materials only (the "Trim to only atlas-solid" option), not to ship DECLARED specs dressed as sourced.
