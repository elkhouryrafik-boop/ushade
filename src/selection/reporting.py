"""The three recovery-reporting artifacts: mass_balance + next_life (D-12, D-14).

These fill the Phase-5/7 EN 15804+A2 dossier shape. Two hard honesty constraints:

  * ``mass_balance`` uses the EXACT reserved field names from ``src/geom/geom.py`` L355-362
    — ``label``, ``scaffold_kg_rented``, ``membrane_m2_recovered``, ``fixings_kg_new`` — so the
    Phase-7 dossier reads ONE consistent shape (Pitfall 10: a renamed field = two shapes).
    The geom.py sidecar reserves these at 0.0 with the note "the Phase-5 carbon stage owns
    the real values"; this module is that owner.
  * ``next_life`` is an ASSUMED placeholder — receiver "receiver TBD — team contact pending"
    VERBATIM. NEVER fabricate a plausible Barcelona cooperative name (Pitfall 9, D-14); it
    flips GROUNDED only when the team supplies the real receiver.

``fixings_kg_new`` = pillar_count × an ASSUMED per-connection fixing mass (A4, labelled ASSUMED).
"""

from __future__ import annotations

# The exact placeholder receiver — copied verbatim from D-14. NEVER replace with an invented name.
NEXT_LIFE_RECEIVER_PLACEHOLDER = "receiver TBD — team contact pending"


def mass_balance(
    *,
    scaffold_kg_rented: float,
    membrane_m2_recovered: float,
    fixings_kg_new: float,
) -> dict:
    """The D-12 mass-balance dict with the EXACT reserved geom.py field names (Pitfall 10).

    Keys are EXACTLY ``{label, scaffold_kg_rented, membrane_m2_recovered, fixings_kg_new}``.
    ``scaffold_kg_rented`` = Phase-4 OUT_BOM scaffold × unit_mass_kg; ``membrane_m2_recovered``
    = selected membrane m²; ``fixings_kg_new`` = pillar_count × ASSUMED per-connection mass.
    """
    return {
        "label": "ASSUMED",
        "scaffold_kg_rented": scaffold_kg_rented,
        "membrane_m2_recovered": membrane_m2_recovered,
        "fixings_kg_new": fixings_kg_new,
    }


def next_life(recovered_m2: float, unit_mass_kg: float) -> dict:
    """The D-14 textile-afterlife record — ASSUMED placeholder, never a fabricated receiver.

    ``status`` is "ASSUMED" and ``receiver`` is the exact placeholder until the team supplies a
    real name (Pitfall 9). ``return_mass_kg`` = recovered m² × unit_mass_kg.
    """
    return {
        "status": "ASSUMED",
        "receiver": NEXT_LIFE_RECEIVER_PLACEHOLDER,
        "return_mass_kg": recovered_m2 * unit_mass_kg,
    }
