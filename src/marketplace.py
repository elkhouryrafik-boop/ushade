import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
import pandas as pd
from config.settings import DATA_DIR

_CONDITION_SCORE = {"excellent": 5, "good": 4, "fair": 3, "poor": 1}


class MarketplaceService:
    def __init__(self):
        self.stakeholders = pd.read_csv(DATA_DIR / "seed_stakeholders.csv", sep="|")
        self.detections = pd.read_csv(DATA_DIR / "seed_detections.csv", sep="|")

        self.detections["availability_start"] = pd.to_datetime(
            self.detections["availability_start"], errors="coerce"
        ).dt.date
        self.detections["availability_end"] = pd.to_datetime(
            self.detections["availability_end"], errors="coerce"
        ).dt.date

        for col in ["quantity_m2", "distance_to_forum_km", "confidence"]:
            if col in self.detections.columns:
                self.detections[col] = pd.to_numeric(self.detections[col], errors="coerce")

    def get_stakeholders(self, stakeholder_type: str | None = None) -> pd.DataFrame:
        if stakeholder_type:
            return self.stakeholders[self.stakeholders["type"] == stakeholder_type]
        return self.stakeholders

    def get_transaction_feed(self) -> list:
        return [
            {
                "description": "demo media operator vinyl matched to a demo festival — 450 m2 — EUR 2,250",
                "material": "PVC billboard vinyl",
                "quantity_m2": 450.0,
                "brokerage_eur": 2250.0,
                "date": "2026-05-14",
                "status": "completed",
            },
            {
                "description": "demo supplier scaffold matched to Ajuntament plaza project — 200 m2 — EUR 1,800",
                "material": "Scaffold tube 48.3mm",
                "quantity_m2": 200.0,
                "brokerage_eur": 1800.0,
                "date": "2026-05-28",
                "status": "completed",
            },
            {
                "description": "a demo refit yard shrink-wrap matched to Brunch Electronik — 80 m2 — EUR 640",
                "material": "PE yacht shrink-wrap",
                "quantity_m2": 80.0,
                "brokerage_eur": 640.0,
                "date": "2026-06-03",
                "status": "pending",
            },
            {
                "description": "Fira BCN carpet matched to Sónar Festival — 300 m2 — EUR 1,500",
                "material": "PP festival carpet",
                "quantity_m2": 300.0,
                "brokerage_eur": 1500.0,
                "date": "2026-06-10",
                "status": "completed",
            },
            {
                "description": "a demo festival truss matched to Cruïlla Festival — 180 m2 — EUR 2,160",
                "material": "Aluminium event truss",
                "quantity_m2": 180.0,
                "brokerage_eur": 2160.0,
                "date": "2026-06-15",
                "status": "negotiating",
            },
            {
                "description": "Port BCN netting matched to IAAC research project — 120 m2 — EUR 600",
                "material": "Industrial shade net (HDPE)",
                "quantity_m2": 120.0,
                "brokerage_eur": 600.0,
                "date": "2026-06-18",
                "status": "pending",
            },
        ]

    def match(
        self,
        material_code: str,
        quantity_m2_needed: float,
        event_date_str: str,
        max_distance_km: float = 50,
    ) -> pd.DataFrame:
        try:
            event_date = datetime.date.fromisoformat(event_date_str)
        except Exception:
            event_date = datetime.date.today() + datetime.timedelta(days=30)

        df = self.detections.copy()

        # material type fit — only keep records that have this code
        df["material_type_fit"] = df["material_codes"].apply(
            lambda x: 1 if material_code in str(x).split(";") else 0
        )
        df = df[df["material_type_fit"] == 1]

        if df.empty:
            return df

        # timing fit — event date must fall inside availability window
        df["timing_fit"] = df.apply(
            lambda r: 1 if (
                pd.notna(r["availability_start"]) and pd.notna(r["availability_end"])
                and r["availability_start"] <= event_date <= r["availability_end"]
            ) else 0,
            axis=1,
        )
        df = df[df["timing_fit"] == 1]

        if df.empty:
            return df

        # distance filter
        df = df[df["distance_to_forum_km"] <= max_distance_km]

        if df.empty:
            return df

        # scoring
        df["quantity_fit"] = (df["quantity_m2"] / quantity_m2_needed).clip(upper=1.0)

        def dist_score(d):
            if d <= 5: return 5
            if d <= 15: return 4
            if d <= 25: return 3
            if d <= 35: return 2
            return 1

        def cond_score(c):
            return _CONDITION_SCORE.get(str(c).lower(), 2)

        df["distance_score"] = df["distance_to_forum_km"].apply(dist_score)
        df["condition_score"] = df["condition"].apply(cond_score)
        df["carbon_score"] = df["distance_to_forum_km"].apply(dist_score)

        # normalise quantity_fit to 0–5 scale
        df["composite_score"] = (
            df["quantity_fit"] * 5 * 0.25
            + df["distance_score"] * 0.25
            + df["condition_score"] * 0.25
            + df["carbon_score"] * 0.25
        )

        return df.nlargest(3, "composite_score").reset_index(drop=True)
