import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from config.settings import (
    EF_TRUCK, EF_INSTALL_M2, EF_EOL_M2,
    CARBON_PERMANENT_SHADE_LOW, CARBON_PERMANENT_SHADE_HIGH,
    DATA_DIR, MATERIAL_CODES
)

_materials_cache: pd.DataFrame | None = None


def _get_materials() -> pd.DataFrame:
    global _materials_cache
    if _materials_cache is None:
        _materials_cache = pd.read_csv(DATA_DIR / "seed_materials.csv", sep="|")
    return _materials_cache


def _get_embodied(material_code: str) -> float:
    df = _get_materials()
    row = df[df["code"] == material_code]
    if row.empty:
        return 2.0
    return float(row.iloc[0]["embodied_kgco2e_kg"])


def _get_mass_per_m2(material_code: str) -> float:
    df = _get_materials()
    row = df[df["code"] == material_code]
    if row.empty:
        return 1.0
    return float(row.iloc[0]["mass_kg_m2"])


def calculate_carbon(material_code: str, quantity_kg: float, distance_km: float) -> dict:
    embodied_ef = _get_embodied(material_code)
    embodied_avoided_kg = embodied_ef * quantity_kg

    transport_generated_kg = EF_TRUCK * quantity_kg * distance_km * 2

    mass_per_m2 = _get_mass_per_m2(material_code)
    area_m2 = quantity_kg / mass_per_m2 if mass_per_m2 > 0 else 0
    install_generated_kg = EF_INSTALL_M2 * area_m2

    net_benefit_kg = embodied_avoided_kg - transport_generated_kg - install_generated_kg

    vs_permanent_low = embodied_avoided_kg / (CARBON_PERMANENT_SHADE_LOW * area_m2) if area_m2 > 0 else 0
    vs_permanent_high = embodied_avoided_kg / (CARBON_PERMANENT_SHADE_HIGH * area_m2) if area_m2 > 0 else 0

    return {
        "embodied_avoided_kg": round(embodied_avoided_kg, 2),
        "transport_generated_kg": round(transport_generated_kg, 2),
        "install_generated_kg": round(install_generated_kg, 2),
        "net_benefit_kg": round(net_benefit_kg, 2),
        "vs_permanent_low": round(vs_permanent_low, 4),
        "vs_permanent_high": round(vs_permanent_high, 4),
    }


def carbon_avoided_if_harvested(detection_record: dict) -> float:
    codes_raw = str(detection_record.get("material_codes", ""))
    codes = [c.strip() for c in codes_raw.split(";") if c.strip()]
    quantity_kg = float(detection_record.get("quantity_kg", 0))
    distance_km = float(detection_record.get("distance_to_forum_km", 0))

    if not codes or quantity_kg == 0:
        return 0.0

    kg_per_code = quantity_kg / len(codes)
    total = 0.0
    for code in codes:
        result = calculate_carbon(code, kg_per_code, distance_km)
        total += result["net_benefit_kg"]
    return round(total, 2)


def city_total_carbon_potential(detections_df: pd.DataFrame) -> dict:
    total_kg = float(detections_df["carbon_avoided_kg"].sum()) if "carbon_avoided_kg" in detections_df.columns else 0.0
    total_tonnes = total_kg / 1000
    flights = int(total_kg / 200)
    cars = int(total_kg / 2100)
    return {
        "total_carbon_avoided_kg": round(total_kg, 2),
        "total_carbon_avoided_tonnes": round(total_tonnes, 2),
        "equivalent_flights_bcn_london": flights,
        "equivalent_cars_off_road_year": cars,
    }
