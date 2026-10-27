"""CD-B — Crowd → Heat coupling: the crowd's own heat raises the felt UTCI of its cells.

The missing arrow the danger overlay never modeled: a dense crowd does not just *sit in* hot cells,
it *makes* them hotter. Three deterministic, literature-grounded pathways turn a per-cell crowd
density into a per-cell UTCI rise (ΔUTCI), which is added to the base (sun-driven) UTCI field:

  1. METABOLIC sensible heat  — bodies emit watts; the sensible fraction warms the trapped air.
  2. BLOCKED WIND             — a dense crowd is a porous obstacle; less ventilation → higher UTCI.
  3. SWEAT HUMIDITY           — the latent fraction adds water vapour → higher felt temperature.

PROVENANCE (CLAUDE.md non-negotiable — the whole layer is ASSUMED until calibrated):
  - DERIVED (physics/standards): ρ·c_p of air (1200 J/m³K), per-person met watts (ISO 7730/ASHRAE 55),
    the box-model ΔT form, the Fruin crush ceiling.
  - ASSUMED (must-flag knobs): activity/met choice, sensible fraction at >28 °C, mixing height,
    base wind, wind-block fraction, the UTCI wind/humidity sensitivities, the +ΔUTCI cap.
  - The crowd_density field feeding this is itself ASSUMED (see crowd-density provenance).
  => Net: a crowd→UTCI layer is ASSUMED end-to-end. NEVER claim a measured "+N °C".

Honest science (research `.planning/materials-app/CD-B-CROWD-HEAT-COUPLING-RESEARCH.md`): outdoors the
DRY metabolic warming is small (tenths of °C, advected away); the DOMINANT effect is the indirect
wind-block + humidity penalty (+1..+3 °C felt, up to ~4 °C in sheltered packed crowds — Collins et al.
2024, *Atmosphere* 15:1184). In the hot-dry >35 °C regime wind stops relieving heat strain
(Bröde & Kampmann 2023, *Biology* 12:802), so the penalty bites hardest exactly on a hot August day.

NO infrared call anywhere — pure arithmetic on the existing UTCI grid + the crowd field.
"""

from __future__ import annotations

# ── DERIVED constants (physics / international standards) ─────────────────────────────────────────
RHO_CP_AIR: float = 1200.0      # J/(m³·K) — volumetric heat capacity of air (ρ≈1.2, c_p≈1005). Oke 2017.
FRUIN_MAX_PPL_M2: float = 6.0   # physical crush ceiling (Fruin LOS-F / Still) — clamp the density input.

# ── ASSUMED knobs (literature-bounded, owner-tunable; every one is a labelled assumption) ─────────
P_PERSON_W: float = 150.0       # [ASSUMED] per-person metabolic output — standing/active festival-goer
#                                  (ISO 7730/ASHRAE: 1.2 met≈126 W seated-standing … dancing≈250 W). 150 = mid.
SENSIBLE_FRACTION: float = 0.36  # [ASSUMED] sensible share at hot ambient (~30-35 °C); rest is latent
#                                  (ASHRAE Ch.18 dancing 90/250≈0.36; the room-temp value 0.67 does NOT hold hot).
MIXING_HEIGHT_M: float = 2.5    # [ASSUMED] shallow near-ground canopy the crowd heat accumulates in.
BASE_WIND_MS: float = 2.5       # [ASSUMED] mid-August Barcelona afternoon breeze over open ground.
WIND_BLOCK_FRACTION: float = 0.70  # [ASSUMED] max fractional near-ground wind a packed crowd removes.
K_WIND_UTCI: float = 0.70       # [ASSUMED] °C UTCI rise per 1 m/s of wind lost (UTCI is wind-sensitive at low v).
K_HUMID_UTCI: float = 1.40      # [ASSUMED] °C UTCI rise at full density from sweat humidity (still-air worst case).
DUTCI_CAP_C: float = 4.0        # [ASSUMED] cap on total ΔUTCI — the sheltered-stadium observed bound (Collins 2024).
MIN_WIND_MS: float = 0.30       # floor on local wind so the air-residence time stays finite.


def people_per_m2(agents_in_cell: float, *, people_per_agent: float, cell_size_m: float) -> float:
    """Convert sim agents-in-cell → people/m², clamped at the Fruin crush ceiling.

    The crowd sim runs N = capacity / AGENT_DIVISOR scaled agents, so each agent stands in for
    ``people_per_agent`` real people. The over-packed waypoint cells exceed any physical density, so
    we clamp at FRUIN_MAX_PPL_M2 — honest (a real crowd cannot pack past the crush ceiling) and it
    keeps the coupling physical.
    """
    raw = agents_in_cell * people_per_agent / (cell_size_m * cell_size_m)
    return max(0.0, min(raw, FRUIN_MAX_PPL_M2))


def crowd_utci_delta(ppl_m2: float, *, base_wind_ms: float = BASE_WIND_MS, cell_size_m: float = 6.0) -> dict:
    """ΔUTCI (°C) a cell gains from its OWN crowd, split into the three pathways.

    Returns a dict with each pathway and the capped total. All terms ASSUMED (see module docstring).
    Pure + deterministic — no RNG, no I/O, no infrared.
    """
    d = max(0.0, min(ppl_m2, FRUIN_MAX_PPL_M2))
    frac = d / FRUIN_MAX_PPL_M2                                   # 0..1 crowd "fullness"

    # 2) BLOCKED WIND — porous-obstacle ventilation loss → UTCI rise (the dominant outdoor pathway).
    v_local = base_wind_ms * (1.0 - WIND_BLOCK_FRACTION * frac)
    d_utci_wind = K_WIND_UTCI * (base_wind_ms - v_local)

    # 1) METABOLIC sensible heat → air-temp rise (box model; air sits in the cell for tau = cell/v_local).
    q_sensible = d * P_PERSON_W * SENSIBLE_FRACTION              # W/m²
    tau = cell_size_m / max(v_local, MIN_WIND_MS)               # s — air residence time in the cell
    d_temp_metabolic = q_sensible * tau / (RHO_CP_AIR * MIXING_HEIGHT_M)  # °C (≈ ΔUTCI via ∂UTCI/∂Ta≈1)

    # 3) SWEAT HUMIDITY — latent load adds vapour → felt UTCI rise; worse in still (poorly ventilated) air.
    still = 1.0 - 0.5 * (v_local / base_wind_ms) if base_wind_ms > 0 else 1.0
    d_utci_humidity = K_HUMID_UTCI * frac * still

    total = d_temp_metabolic + d_utci_wind + d_utci_humidity
    total_capped = min(total, DUTCI_CAP_C)
    return {
        "ppl_m2": d,
        "fullness": frac,
        "v_local_ms": v_local,
        "d_temp_metabolic": d_temp_metabolic,
        "d_utci_wind": d_utci_wind,
        "d_utci_humidity": d_utci_humidity,
        "d_utci_total": total_capped,
        "capped": total > DUTCI_CAP_C,
        "tier": "ASSUMED",   # whole layer — never promote without a calibrated coupled-sim validation
    }


def adjusted_utci(base_utci_c: float, ppl_m2: float, **kw) -> float:
    """Base (sun-driven) UTCI + the crowd's own ΔUTCI = the felt UTCI the crowd actually experiences."""
    return base_utci_c + crowd_utci_delta(ppl_m2, **kw)["d_utci_total"]


if __name__ == "__main__":
    # Sanity: light vs packed crowd on a hot base, all pathways visible.
    for d in (0.0, 1.8, 4.0, 6.0):
        r = crowd_utci_delta(d)
        print(f"{d:>4.1f} ppl/m² -> +{r['d_utci_total']:.2f} °C UTCI "
              f"(metabolic {r['d_temp_metabolic']:.2f}, wind {r['d_utci_wind']:.2f}, "
              f"humidity {r['d_utci_humidity']:.2f}; v_local {r['v_local_ms']:.2f} m/s"
              f"{', CAPPED' if r['capped'] else ''})")
