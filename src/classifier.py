import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from config.settings import DATA_DIR, MATERIAL_CODES
from src.llm_provider import complete, provider_name

_KEYWORD_MAP = {
    "NET": ["netting", "net", "mesh", "hdpe", "shade net", "knit"],
    "PVC": ["vinyl", "billboard", "pvc", "banner", "sign", "flex"],
    "SCF": ["scaffold", "tube", "pipe", "steel tube", "scaffolding", "48.3"],
    "ALU": ["truss", "aluminium", "aluminum", "stage", "alu", "alloy"],
    "PAL": ["pallet", "wood", "timber", "epal", "wooden"],
    "HRS": ["fence", "heras", "panel", "barrier", "fencing", "mesh panel"],
    "CHR": ["chair", "seat", "seating", "stadium", "bleacher"],
    "TRP": ["tarp", "tarpaulin", "cover", "ground sheet", "woven pe"],
    "SHR": ["shrink", "yacht", "marine", "boat", "ldpe", "shrink-wrap", "sailcloth"],
    "CRP": ["carpet", "floor", "flooring", "mat", "needle-punch", "pp carpet"],
}

_APPLICATIONS = {
    "SCF": ["Shade corridor spine", "Stage frame", "Canopy support structure"],
    "ALU": ["Main stage roof canopy", "Branded span", "Truss arch"],
    "PAL": ["Festival flooring", "Seating platform", "Furniture base"],
    "HRS": ["Perimeter barrier", "Wind screen", "Partition wall"],
    "CHR": ["Tiered grandstand", "Outdoor seating", "Festival furniture"],
    "PVC": ["Shade membrane canopy", "Rain cover", "Projection surface"],
    "NET": ["Ventilated cooling corridor", "Shade screen", "Climber support"],
    "TRP": ["Rain shelter", "Ground protection", "Backstage cover"],
    "SHR": ["Translucent roof canopy", "Premium rain cover", "Light-diffusing membrane"],
    "CRP": ["Stage floor", "Lounge floor", "Festival pathway"],
}

_CONDITION_DEFAULT = {
    "excellent": 0.95, "good": 0.80, "fair": 0.65, "poor": 0.40
}

_MATERIAL_TYPE = {
    "SCF": "STRUCTURE", "ALU": "STRUCTURE", "PAL": "STRUCTURE",
    "HRS": "STRUCTURE", "CHR": "STRUCTURE",
    "PVC": "MEMBRANE", "NET": "MEMBRANE", "TRP": "MEMBRANE",
    "SHR": "MEMBRANE", "CRP": "MEMBRANE",
}


class MaterialClassifier:
    def __init__(self):
        self.materials = pd.read_csv(DATA_DIR / "seed_materials.csv", sep="|")
        self._material_context = self._build_material_context()

    def _build_material_context(self) -> str:
        lines = ["Known material codes:\n"]
        for _, row in self.materials.iterrows():
            lines.append(
                f"- {row['code']}: {row['name']} | type: {row['type']} | "
                f"category: {row['category']} | embodied: {row['embodied_kgco2e_kg']} kgCO2e/kg | "
                f"typical use: {row['typical_use']}"
            )
        return "\n".join(lines)

    def _offline_classify(self, description: str) -> dict:
        desc_lower = description.lower()
        scores = {code: 0 for code in MATERIAL_CODES}
        for code, keywords in _KEYWORD_MAP.items():
            for kw in keywords:
                if kw in desc_lower:
                    scores[code] += 1

        best_code = max(scores, key=lambda c: scores[c])
        best_score = scores[best_code]

        if best_score == 0:
            best_code = "NET"
            confidence = 0.20
        else:
            confidence = min(0.50 + best_score * 0.10, 0.80)

        condition = "good"
        for word in ["excellent", "new", "pristine"]:
            if word in desc_lower:
                condition = "excellent"
                break
        for word in ["fair", "worn", "faded", "used"]:
            if word in desc_lower:
                condition = "fair"
                break
        for word in ["poor", "damaged", "torn", "broken"]:
            if word in desc_lower:
                condition = "poor"
                break

        priority = "HIGH" if confidence > 0.65 else ("MEDIUM" if confidence > 0.45 else "LOW")

        mat_row = self.materials[self.materials["code"] == best_code]
        embodied = float(mat_row.iloc[0]["embodied_kgco2e_kg"]) if not mat_row.empty else 2.0
        carbon_est = embodied * 50

        his = round(2.5 + confidence * 2, 1)
        his = min(his, 5.0)

        return {
            "best_match_code": best_code,
            "best_match_name": MATERIAL_CODES.get(best_code, best_code),
            "confidence": round(confidence, 2),
            "condition_rating": condition,
            "recommended_applications": _APPLICATIONS.get(best_code, []),
            "collection_priority": priority,
            "carbon_avoided_estimate_kg": round(carbon_est, 1),
            "his_score_estimate": his,
            "theory_cite": "Urban Cooling Cookbook (Erell et al. 2011)",
            "data_cite": "Material availability from live detection database",
            "raw_response": f"[offline] keyword match → {best_code}",
            "is_new_material": False,
            "new_material_suggestion": None,
            "used_offline": True,
        }

    def _llm_classify(self, description: str) -> dict | None:
        system = (
            "You are a material classification AI for the Material Harvesting Engine platform. "
            "You classify urban surplus and waste materials using the following known codes.\n\n"
            + self._material_context
            + "\n\nRespond in this exact format:\n"
            "CODE: <code>\n"
            "CONFIDENCE: <0.0 to 1.0>\n"
            "CONDITION: <excellent|good|fair|poor>\n"
            "PRIORITY: <HIGH|MEDIUM|LOW>\n"
            "APPLICATIONS: <comma-separated list>\n"
            "CARBON_ESTIMATE_KG: <float>\n"
            "HIS_SCORE: <1.0 to 5.0>\n"
            "THEORY: <one citation>\n"
            "DATA: <one data source>\n"
            "IS_NEW: <yes|no>\n"
            "NEW_SUGGESTION: <suggestion or none>\n"
        )
        messages = [{"role": "user", "content": f"Classify this material: {description}"}]
        raw = complete(system, messages, max_tokens=500)
        if not raw:
            return None
        try:
            def extract(key):
                m = re.search(rf"^{key}:\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
                return m.group(1).strip() if m else ""

            code = extract("CODE").upper()
            if code not in MATERIAL_CODES:
                code = "NET"
            confidence = float(extract("CONFIDENCE") or 0.70)
            condition = extract("CONDITION").lower() or "good"
            priority = extract("PRIORITY").upper() or "MEDIUM"
            apps_raw = extract("APPLICATIONS")
            apps = [a.strip() for a in apps_raw.split(",") if a.strip()] or _APPLICATIONS.get(code, [])
            carbon_est = float(extract("CARBON_ESTIMATE_KG") or 100)
            his = float(extract("HIS_SCORE") or 3.0)
            theory = extract("THEORY") or "Urban Cooling Cookbook (Erell 2011)"
            data = extract("DATA") or "Live detection database"
            is_new = extract("IS_NEW").lower() == "yes"
            new_sug = extract("NEW_SUGGESTION")
            if new_sug.lower() in ("none", ""):
                new_sug = None

            return {
                "best_match_code": code,
                "best_match_name": MATERIAL_CODES.get(code, code),
                "confidence": round(min(max(confidence, 0), 1), 2),
                "condition_rating": condition,
                "recommended_applications": apps,
                "collection_priority": priority,
                "carbon_avoided_estimate_kg": round(carbon_est, 1),
                "his_score_estimate": round(min(max(his, 1.0), 5.0), 1),
                "theory_cite": theory,
                "data_cite": data,
                "raw_response": raw,
                "is_new_material": is_new,
                "new_material_suggestion": new_sug,
                "used_offline": False,
            }
        except Exception:
            return None

    def classify(self, description: str, image_filename: str | None = None) -> dict:
        if provider_name() != "offline":
            result = self._llm_classify(description)
            if result:
                return result
        return self._offline_classify(description)

    def classify_image(self, filename: str, metadata: dict | None = None) -> dict:
        parts = Path(filename).stem.replace("_", " ").replace("-", " ")
        desc = f"[Simulated computer vision] Image filename: {parts}."
        if metadata:
            desc += " Metadata: " + "; ".join(f"{k}={v}" for k, v in metadata.items())
        result = self.classify(desc)
        result["raw_response"] = "[simulated CV] " + result.get("raw_response", "")
        return result
