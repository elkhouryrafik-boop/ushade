import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
import pandas as pd
from config.settings import DATA_DIR, MATERIAL_CODES

TODAY = datetime.date.today()


class DetectionService:
    def __init__(self):
        self.detections = pd.read_csv(DATA_DIR / "seed_detections.csv", sep="|")
        self.materials = pd.read_csv(DATA_DIR / "seed_materials.csv", sep="|")

        self.detections["availability_start"] = pd.to_datetime(
            self.detections["availability_start"], errors="coerce"
        ).dt.date
        self.detections["availability_end"] = pd.to_datetime(
            self.detections["availability_end"], errors="coerce"
        ).dt.date

        for col in ["quantity_m2", "quantity_kg", "distance_to_forum_km",
                    "confidence", "carbon_avoided_kg", "location_lat", "location_lon"]:
            if col in self.detections.columns:
                self.detections[col] = pd.to_numeric(self.detections[col], errors="coerce")

    def _compute_status(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        today = TODAY
        seven_days = today + datetime.timedelta(days=7)
        thirty_days = today + datetime.timedelta(days=30)
        ninety_days = today + datetime.timedelta(days=90)

        def row_status(row):
            start = row["availability_start"]
            end = row["availability_end"]
            if pd.isna(start) or pd.isna(end):
                return "unknown"
            if end <= seven_days:
                return "expiring"
            if start <= today < end:
                return "available_now"
            if today < start <= thirty_days:
                return "available_30d"
            if thirty_days < start <= ninety_days:
                return "available_90d"
            return "future"

        df["status"] = df.apply(row_status, axis=1)
        return df

    def get_all(self) -> pd.DataFrame:
        return self._compute_status(self.detections)

    def get_summary(self) -> dict:
        df = self.get_all()
        all_codes = []
        for codes_str in df["material_codes"].dropna():
            for code in str(codes_str).split(";"):
                c = code.strip()
                if c:
                    all_codes.append(c)
        unique_codes = list(set(all_codes))

        expiring = df[df["status"] == "expiring"]
        available_now = df[df["status"] == "available_now"]

        return {
            "total_sources": len(df),
            "total_m2": float(df["quantity_m2"].sum()),
            "total_kg": float(df["quantity_kg"].sum()),
            "total_carbon_avoided_kg": float(df["carbon_avoided_kg"].sum()),
            "total_carbon_avoided_tonnes": round(float(df["carbon_avoided_kg"].sum()) / 1000, 2),
            "materials_detected": unique_codes,
            "expiring_count": len(expiring),
            "available_now_count": len(available_now),
        }

    def get_expiring(self, days: int = 7) -> pd.DataFrame:
        df = self.get_all()
        cutoff = TODAY + datetime.timedelta(days=days)
        return df[df["availability_end"] <= cutoff]

    def filter(
        self,
        source_type=None,
        material_code=None,
        max_distance_km=None,
        condition=None,
    ) -> pd.DataFrame:
        df = self.get_all()
        if source_type:
            if isinstance(source_type, list):
                df = df[df["source_type"].isin(source_type)]
            else:
                df = df[df["source_type"] == source_type]
        if material_code:
            if isinstance(material_code, list):
                mask = df["material_codes"].apply(
                    lambda x: any(c in str(x).split(";") for c in material_code)
                )
            else:
                mask = df["material_codes"].apply(
                    lambda x: material_code in str(x).split(";")
                )
            df = df[mask]
        if max_distance_km is not None:
            df = df[df["distance_to_forum_km"] <= max_distance_km]
        if condition:
            if isinstance(condition, list):
                df = df[df["condition"].isin(condition)]
            else:
                df = df[df["condition"] == condition]
        return df

    def get_material_name(self, code: str) -> str:
        row = self.materials[self.materials["code"] == code]
        if not row.empty:
            return str(row.iloc[0]["name"])
        return MATERIAL_CODES.get(code, code)

    def to_map_data(self) -> list:
        df = self.get_all()
        result = []
        for _, row in df.iterrows():
            result.append({
                "lat": row.get("location_lat"),
                "lon": row.get("location_lon"),
                "source_name": row.get("source_name"),
                "status": row.get("status"),
                "material_codes": row.get("material_codes"),
                "quantity_m2": row.get("quantity_m2"),
                "carbon_avoided_kg": row.get("carbon_avoided_kg"),
                "contact": row.get("contact"),
                "distance_to_forum_km": row.get("distance_to_forum_km"),
            })
        return result
