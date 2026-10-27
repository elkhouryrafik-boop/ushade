import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
import random
import pandas as pd


class PredictionEngine:
    def __init__(self):
        self.today = datetime.date.today()

    # ---------- individual prediction streams ----------

    def billboard_rotations(self, n: int = 6) -> list:
        results = []
        base = self.today + datetime.timedelta(days=7)
        for i in range(n):
            d = base + datetime.timedelta(days=14 * i)
            results.append({
                "event": "demo media operator billboard rotation",
                "source": "demo media operator Barcelona",
                "material_codes": ["PVC"],
                "quantity_m2_min": 200,
                "quantity_m2_max": 800,
                "date": d,
                "confidence": 0.90,
                "source_type": "advertising",
                "lat": 41.345,
                "lon": 2.037,
            })
        return results

    def festival_calendar(self) -> list:
        return [
            {
                "event": "a demo festival teardown",
                "source": "a demo festival",
                "material_codes": ["ALU", "HRS", "CRP", "SCF"],
                "quantity_m2_min": 700,
                "quantity_m2_max": 900,
                "date": datetime.date(2026, 6, 10),
                "confidence": 0.95,
                "source_type": "festival",
                "lat": 41.411,
                "lon": 2.221,
            },
            {
                "event": "Sónar Festival teardown",
                "source": "Sónar Festival",
                "material_codes": ["ALU", "CRP", "HRS"],
                "quantity_m2_min": 300,
                "quantity_m2_max": 400,
                "date": datetime.date(2026, 6, 22),
                "confidence": 0.92,
                "source_type": "festival",
                "lat": 41.354,
                "lon": 2.130,
            },
            {
                "event": "Cruïlla Festival teardown",
                "source": "Cruïlla Festival",
                "material_codes": ["HRS", "SCF", "CRP"],
                "quantity_m2_min": 250,
                "quantity_m2_max": 350,
                "date": datetime.date(2026, 7, 12),
                "confidence": 0.90,
                "source_type": "festival",
                "lat": 41.411,
                "lon": 2.221,
            },
            {
                "event": "a demo festival teardown",
                "source": "a demo festival",
                "material_codes": ["ALU", "CHR", "CRP"],
                "quantity_m2_min": 180,
                "quantity_m2_max": 260,
                "date": datetime.date(2026, 7, 28),
                "confidence": 0.85,
                "source_type": "festival",
                "lat": 41.364,
                "lon": 2.156,
            },
            {
                "event": "Brunch Electronik teardown",
                "source": "Brunch Electronik",
                "material_codes": ["HRS", "CRP", "PAL"],
                "quantity_m2_min": 150,
                "quantity_m2_max": 210,
                "date": datetime.date(2026, 8, 22),
                "confidence": 0.88,
                "source_type": "festival",
                "lat": 41.411,
                "lon": 2.221,
            },
        ]

    def construction_wave(self, months_ahead: int = 6) -> list:
        results = []
        for i in range(months_ahead):
            d = self.today.replace(day=1) + datetime.timedelta(days=32 * i)
            d = d.replace(day=15)
            month = d.month
            if 3 <= month <= 5:
                qty_min, qty_max, conf = 400, 800, 0.55
                label = "Spring construction wave — scaffold & formwork"
            elif 9 <= month <= 11:
                qty_min, qty_max, conf = 350, 700, 0.50
                label = "Autumn construction wave — scaffold & formwork"
            else:
                qty_min, qty_max, conf = 120, 300, 0.40
                label = "Off-peak construction returns — scaffold"
            results.append({
                "event": label,
                "source": "BCN Construction Sector (aggregate)",
                "material_codes": ["SCF", "HRS"],
                "quantity_m2_min": qty_min,
                "quantity_m2_max": qty_max,
                "date": d,
                "confidence": conf,
                "source_type": "construction",
                "lat": 41.390,
                "lon": 2.170,
            })
        return results

    def port_cycle(self, months_ahead: int = 6) -> list:
        results = []
        for i in range(months_ahead):
            d = self.today.replace(day=1) + datetime.timedelta(days=32 * i)
            d = d.replace(day=20)
            month = d.month
            if month in (10, 11, 12, 1, 2, 3, 4):
                results.append({
                    "event": "a demo refit yard refit season — shrink-wrap and netting",
                    "source": "a demo refit yard Superyacht Yard",
                    "material_codes": ["SHR", "NET"],
                    "quantity_m2_min": 15,
                    "quantity_m2_max": 65,
                    "date": d,
                    "confidence": 0.75,
                    "source_type": "port",
                    "lat": 41.385,
                    "lon": 2.196,
                })
        return results

    def ulma_pipeline(self, months_ahead: int = 3) -> list:
        results = []
        for i in range(months_ahead * 2):
            d = self.today + datetime.timedelta(days=14 * (i + 1))
            qty_min = 80 * 3
            qty_max = 200 * 5
            results.append({
                "event": "demo supplier scaffold return — site closures",
                "source": "demo supplier Construccio",
                "material_codes": ["SCF", "HRS"],
                "quantity_m2_min": qty_min,
                "quantity_m2_max": qty_max,
                "date": d,
                "confidence": 0.65,
                "source_type": "construction",
                "lat": 41.566,
                "lon": 2.158,
            })
        return results

    def all_predictions(self, months_ahead: int = 6) -> pd.DataFrame:
        rows = []
        for p in (
            self.billboard_rotations(n=months_ahead * 2)
            + self.festival_calendar()
            + self.construction_wave(months_ahead)
            + self.port_cycle(months_ahead)
            + self.ulma_pipeline(min(months_ahead, 3))
        ):
            rows.append({
                "date": p["date"],
                "event": p["event"],
                "source": p["source"],
                "material_codes": ", ".join(p["material_codes"]),
                "quantity_m2_min": p["quantity_m2_min"],
                "quantity_m2_max": p["quantity_m2_max"],
                "confidence": p["confidence"],
                "source_type": p["source_type"],
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df

    def monthly_forecast(self, months_ahead: int = 6) -> pd.DataFrame:
        from config.settings import MATERIAL_CODES
        df = self.all_predictions(months_ahead)
        if df.empty:
            return pd.DataFrame()

        df["midpoint"] = (df["quantity_m2_min"] + df["quantity_m2_max"]) / 2
        df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

        codes = list(MATERIAL_CODES.keys())
        months = sorted(df["month"].unique())
        result = {m: {c: 0.0 for c in codes} for m in months}

        for _, row in df.iterrows():
            m = row["month"]
            for code in [c.strip() for c in str(row["material_codes"]).split(",")]:
                if code in result[m]:
                    result[m][code] += row["midpoint"] / max(
                        len([c.strip() for c in str(row["material_codes"]).split(",")]), 1
                    )

        rows = []
        for month in months:
            r = {"month": str(month)}
            r.update(result[month])
            rows.append(r)
        return pd.DataFrame(rows)

    def gap_analysis(self, monthly_forecast_df: pd.DataFrame) -> list:
        warnings = []
        if monthly_forecast_df.empty:
            return warnings
        from config.settings import MATERIAL_CODES
        codes = [c for c in MATERIAL_CODES.keys() if c in monthly_forecast_df.columns]
        for _, row in monthly_forecast_df.iterrows():
            month = row.get("month", "?")
            for code in codes:
                val = row.get(code, 0)
                if val < 100:
                    warnings.append(
                        f"LOW STOCK WARNING — {month}: {code} predicted only {val:.0f} m2 (threshold 100 m2)"
                    )
        return warnings
