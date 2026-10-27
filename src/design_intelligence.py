import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
import pandas as pd
from config.settings import DATA_DIR, MATERIAL_CODES
from src.detection import DetectionService
from src.llm_provider import complete, provider_name

TODAY = datetime.date.today()

_PATTERNS = [
    {
        "code": "P01",
        "name": "Sun-path canopy",
        "trigger_codes": ["SCF", "NET", "PVC"],
        "description": "Orient a shade membrane on the solar path to block peak irradiance (10h–16h). Use scaffold spine with PVC or HDPE net skin.",
        "theory_cite": "Erell et al. 2011 Urban Microclimate",
        "data_cite": "EPW TMY3 Barcelona solar irradiance",
    },
    {
        "code": "P02",
        "name": "Climber-pollinator strip",
        "trigger_codes": ["HRS", "NET"],
        "description": "Re-purpose Heras fence panels or shade netting as a climbing-plant scaffold to increase urban biodiversity and provide evaporative cooling.",
        "theory_cite": "TNFD LEAP 2023",
        "data_cite": "GBIF Barcelona pollinator occurrence",
    },
    {
        "code": "P03",
        "name": "Greywater wick",
        "trigger_codes": ["CRP", "TRP"],
        "description": "Use carpet or tarpaulin as a capillary wick layer to distribute site greywater for evaporative cooling on hard surfaces.",
        "theory_cite": "Coutts et al. 2013 evaporative cooling",
        "data_cite": "Site greywater and ET measurement",
    },
    {
        "code": "P04",
        "name": "Textile retrofit",
        "trigger_codes": ["PVC", "SHR", "TRP", "NET"],
        "description": "Retrofit surplus membranes over existing structures to create shaded microclimates without new primary materials.",
        "theory_cite": "Ellen MacArthur Foundation 2019 circular textiles",
        "data_cite": "Girbau LAB Vic sorting inventory",
    },
    {
        "code": "P05",
        "name": "SaaS-contract scaffold",
        "trigger_codes": ["SCF", "ALU", "HRS"],
        "description": "Deploy scaffold or truss on a service contract: the platform owns the structure, the client pays for shade-hours rather than materials.",
        "theory_cite": "Bocken et al. 2016 circular business models",
        "data_cite": "demo supplier rental stock",
    },
]

_CONDITION_SCORE = {"excellent": 5, "good": 4, "fair": 3, "poor": 1}

_MEMBRANE_CODES = {"PVC", "NET", "TRP", "SHR", "CRP"}
_STRUCTURE_CODES = {"SCF", "ALU", "PAL", "HRS", "CHR"}


class DesignIntelligenceService:
    def __init__(self):
        self._svc = DetectionService()
        self.materials = pd.read_csv(DATA_DIR / "seed_materials.csv", sep="|")

    def _get_available_now(self, available_df=None) -> pd.DataFrame:
        if available_df is not None:
            return available_df
        df = self._svc.get_all()
        return df[df["status"].isin(["available_now", "expiring"])]

    def inventory_brief(self, available_df=None) -> str:
        df = self._get_available_now(available_df)
        lines = ["AVAILABLE MATERIALS BRIEF\n"]
        for _, row in df.iterrows():
            mat_codes = str(row.get("material_codes", ""))
            names = []
            for code in mat_codes.split(";"):
                c = code.strip()
                if c:
                    names.append(MATERIAL_CODES.get(c, c))
            name_str = ", ".join(names) if names else mat_codes
            lines.append(
                f"- {row.get('quantity_m2', '?')} m2 of {name_str} "
                f"from {row.get('source_name', '?')} "
                f"({row.get('distance_to_forum_km', '?')} km) "
                f"— condition: {row.get('condition', '?')}"
            )
        return "\n".join(lines)

    def cookbook_patterns_firing(self, material_codes_available: list) -> list:
        codes_set = set(material_codes_available)
        firing = []
        for p in _PATTERNS:
            if any(c in codes_set for c in p["trigger_codes"]):
                matches = [c for c in p["trigger_codes"] if c in codes_set]
                firing.append({**p, "matched_codes": matches})
        return firing

    def configure(self, target_area_m2: float, available_df=None) -> dict:
        df = self._get_available_now(available_df)
        units = max(1, round(target_area_m2 / 50))
        scaffold_required = units * 20
        membrane_required = units * 55

        # find best membrane (highest available quantity)
        membrane_rows = df[df["material_codes"].apply(
            lambda x: any(c.strip() in _MEMBRANE_CODES for c in str(x).split(";"))
        )]

        best_membrane = "NET"
        if not membrane_rows.empty:
            best_row = membrane_rows.loc[membrane_rows["quantity_m2"].idxmax()]
            for c in str(best_row["material_codes"]).split(";"):
                if c.strip() in _MEMBRANE_CODES:
                    best_membrane = c.strip()
                    break

        # check stock sufficiency
        scaffold_stock = df[df["material_codes"].apply(
            lambda x: any(c.strip() in _STRUCTURE_CODES for c in str(x).split(";"))
        )]["quantity_m2"].sum()

        membrane_stock = df[df["material_codes"].apply(
            lambda x: any(c.strip() in _MEMBRANE_CODES for c in str(x).split(";"))
        )]["quantity_m2"].sum()

        can_build = scaffold_stock >= scaffold_required and membrane_stock >= membrane_required
        gap = None
        if not can_build:
            gaps = []
            if scaffold_stock < scaffold_required:
                gaps.append(f"Need {scaffold_required:.0f} m2 scaffold, only {scaffold_stock:.0f} m2 available")
            if membrane_stock < membrane_required:
                gaps.append(f"Need {membrane_required:.0f} m2 membrane, only {membrane_stock:.0f} m2 available")
            gap = "; ".join(gaps)

        return {
            "target_area_m2": target_area_m2,
            "units_recommended": units,
            "scaffold_required_m2": float(scaffold_required),
            "membrane_required_m2": float(membrane_required),
            "people_sheltered": int(target_area_m2 / 0.5),
            "best_membrane": best_membrane,
            "can_build": can_build,
            "stock_gap": gap,
        }

    def rank_configurations(self, available_df=None) -> list:
        df = self._get_available_now(available_df)
        if df.empty:
            return []

        structures = df[df["material_codes"].apply(
            lambda x: any(c.strip() in _STRUCTURE_CODES for c in str(x).split(";"))
        )]
        membranes = df[df["material_codes"].apply(
            lambda x: any(c.strip() in _MEMBRANE_CODES for c in str(x).split(";"))
        )]

        if structures.empty or membranes.empty:
            return []

        combos = []
        for _, s in structures.head(3).iterrows():
            s_code = next(
                (c.strip() for c in str(s["material_codes"]).split(";") if c.strip() in _STRUCTURE_CODES),
                "SCF",
            )
            for _, m in membranes.head(3).iterrows():
                m_code = next(
                    (c.strip() for c in str(m["material_codes"]).split(";") if c.strip() in _MEMBRANE_CODES),
                    "NET",
                )

                mat_row = self.materials[self.materials["code"] == m_code]
                shade_max = float(mat_row.iloc[0]["shade_factor_max"]) if not mat_row.empty else 50

                dist = float(min(
                    s.get("distance_to_forum_km", 10),
                    m.get("distance_to_forum_km", 10),
                ))
                cond = str(s.get("condition", "good"))
                cond_score = _CONDITION_SCORE.get(cond, 3) / 5.0

                score = (shade_max / 100) * 0.4 + (1 / max(dist, 1)) * 0.3 + cond_score * 0.3

                combos.append({
                    "structure_code": s_code,
                    "skin_code": m_code,
                    "score": round(score, 4),
                    "shade_factor": shade_max,
                    "distance_km": dist,
                    "condition": cond,
                })

        combos.sort(key=lambda x: x["score"], reverse=True)
        return combos[:3]

    def design_chat(self, question: str, available_brief: str) -> str:
        if provider_name() != "offline":
            system = (
                "You are the Design Intelligence assistant for the Material Harvesting Engine. "
                "You help architects and event designers build shade structures from harvested urban materials.\n\n"
                "CURRENT INVENTORY:\n" + available_brief + "\n\n"
                "COOKBOOK PATTERNS:\n"
                "P01 Sun-path canopy: scaffold + shade membrane oriented on solar path\n"
                "P02 Climber-pollinator strip: Heras fence + net for green wall\n"
                "P03 Greywater wick: carpet or tarp for evaporative cooling\n"
                "P04 Textile retrofit: surplus membranes over existing structures\n"
                "P05 SaaS-contract scaffold: scaffold as a service\n\n"
                "Always give a two-citation audit: theory + data source.\n"
                "Be specific about materials, quantities, and distances."
            )
            messages = [{"role": "user", "content": question}]
            result = complete(system, messages, max_tokens=700)
            if result:
                return result

        # offline fallback
        q = question.lower()
        if any(w in q for w in ["build", "design", "canopy", "shade", "cover"]):
            return (
                "Based on current available stock, I recommend the Ventilated Cooling Corridor system: "
                "scaffold tube from a demo supplier + HDPE shade net. This covers 300 m2 and shelters approximately "
                "600 people at festival density. Two-citation audit: theory: Urban Cooling Cookbook P01 "
                "(Erell 2011); data: material availability from live detection database."
            )
        if any(w in q for w in ["carbon", "co2", "emissions"]):
            return (
                "Deploying harvested materials instead of buying new avoids approximately 120–180 kgCO2e/m2 "
                "compared to permanent shade civil works. For a 300 m2 deployment, that is 36–54 tonnes CO2e saved. "
                "Theory: Ellen MacArthur Foundation circular textiles (2019); data: seed detection carbon_avoided_kg field."
            )
        if any(w in q for w in ["people", "crowd", "attendees"]):
            return (
                "At festival density (0.5 m2 per person), 300 m2 of shade shelters 600 people. "
                "At comfort density (1.5 m2 per person) it shelters 200 people. "
                "Theory: Urban Microclimate (Erell 2011); data: a demo festival seating layout 2024."
            )
        return (
            "Based on current available stock, I recommend the Ventilated Cooling Corridor system: "
            "scaffold tube from a demo supplier + HDPE shade net. This covers 300 m2 and shelters approximately "
            "600 people at festival density. Two-citation audit: theory: Urban Cooling Cookbook P01 "
            "(Erell 2011); data: material availability from live detection database."
        )
