import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import datetime
import math
import pandas as pd
from config.settings import SITE_LAT, SITE_LON, EF_TRUCK

KM_PER_DEGREE = 111.0
AVG_SPEED_KMH = 30.0
COST_PER_KM_EUR = 1.20
COST_NEW_M2 = 60.0
COST_HARVESTED_M2 = 20.0
EMBODIED_AVOIDED_PER_M2 = 2.5


def _euclidean_km(lat1, lon1, lat2, lon2) -> float:
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    deg = math.sqrt(dlat ** 2 + dlon ** 2)
    return deg * KM_PER_DEGREE


class LogisticsOptimiser:
    def __init__(self):
        self.depot_lat = SITE_LAT
        self.depot_lon = SITE_LON

    def nearest_neighbour_route(self, pickup_points: list, vehicle_capacity_kg: float) -> dict:
        if not pickup_points:
            return {
                "route": [],
                "total_distance_km": 0,
                "total_time_hours": 0,
                "total_transport_carbon_kg": 0,
                "collection_cost_eur": 0,
                "capacity_warning": False,
                "capacity_utilisation_pct": 0,
            }

        total_kg = sum(p.get("quantity_kg", 0) for p in pickup_points)
        capacity_warning = total_kg > vehicle_capacity_kg

        unvisited = list(enumerate(pickup_points))
        current_lat, current_lon = self.depot_lat, self.depot_lon
        route = []
        cumulative_km = 0.0
        current_time = datetime.datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)

        stop = 0
        while unvisited:
            nearest_idx = None
            nearest_dist = float("inf")
            for i, p in unvisited:
                d = _euclidean_km(current_lat, current_lon, p["lat"], p["lon"])
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = i

            picked = next((p for i, p in unvisited if i == nearest_idx), None)
            unvisited = [(i, p) for i, p in unvisited if i != nearest_idx]

            cumulative_km += nearest_dist
            travel_hours = nearest_dist / AVG_SPEED_KMH
            current_time += datetime.timedelta(hours=travel_hours)

            stop += 1
            route.append({
                "stop": stop,
                "name": picked.get("name", f"Stop {stop}"),
                "material": picked.get("material", ""),
                "quantity_kg": picked.get("quantity_kg", 0),
                "lat": picked["lat"],
                "lon": picked["lon"],
                "cumulative_km": round(cumulative_km, 2),
                "estimated_arrival": current_time.strftime("%H:%M"),
            })
            current_lat, current_lon = picked["lat"], picked["lon"]

        # return to depot
        return_dist = _euclidean_km(current_lat, current_lon, self.depot_lat, self.depot_lon)
        cumulative_km += return_dist
        return_hours = return_dist / AVG_SPEED_KMH
        current_time += datetime.timedelta(hours=return_hours)
        stop += 1
        route.append({
            "stop": stop,
            "name": "DEPOT — Parc del Fòrum",
            "material": "—",
            "quantity_kg": 0,
            "lat": self.depot_lat,
            "lon": self.depot_lon,
            "cumulative_km": round(cumulative_km, 2),
            "estimated_arrival": current_time.strftime("%H:%M"),
        })

        total_carbon = EF_TRUCK * total_kg * cumulative_km
        collection_cost = cumulative_km * COST_PER_KM_EUR
        utilisation = (total_kg / vehicle_capacity_kg * 100) if vehicle_capacity_kg > 0 else 0

        return {
            "route": route,
            "total_distance_km": round(cumulative_km, 2),
            "total_time_hours": round(cumulative_km / AVG_SPEED_KMH, 2),
            "total_transport_carbon_kg": round(total_carbon, 3),
            "collection_cost_eur": round(collection_cost, 2),
            "capacity_warning": capacity_warning,
            "capacity_utilisation_pct": round(utilisation, 1),
        }

    def carbon_comparison(self, total_transport_carbon_kg: float, total_quantity_m2: float) -> dict:
        embodied_avoided = EMBODIED_AVOIDED_PER_M2 * total_quantity_m2
        net_benefit = embodied_avoided - total_transport_carbon_kg
        eur_saved = (COST_NEW_M2 - COST_HARVESTED_M2) * total_quantity_m2
        return {
            "transport_carbon_generated_kg": round(total_transport_carbon_kg, 3),
            "embodied_carbon_avoided_kg": round(embodied_avoided, 2),
            "net_benefit_kg": round(net_benefit, 2),
            "net_benefit_is_positive": net_benefit > 0,
            "vs_buying_new_eur_saved": round(eur_saved, 2),
        }

    def build_schedule(self, festival_date_str: str, pickup_points: list) -> list:
        try:
            festival_date = datetime.date.fromisoformat(festival_date_str)
        except Exception:
            festival_date = datetime.date.today() + datetime.timedelta(days=14)

        total_kg = sum(p.get("quantity_kg", 0) for p in pickup_points)
        collection_days = max(1, int(total_kg / 200))
        prep_days = 3

        schedule = []
        collect_start = festival_date - datetime.timedelta(days=prep_days + collection_days)
        for i, p in enumerate(pickup_points):
            pick_date = collect_start + datetime.timedelta(days=i // 2)
            schedule.append({
                "action": "COLLECT",
                "supplier": p.get("name", f"Supplier {i+1}"),
                "material": p.get("material", ""),
                "quantity_kg": p.get("quantity_kg", 0),
                "recommended_date": str(pick_date),
                "days_before_festival": (festival_date - pick_date).days,
            })

        clean_date = festival_date - datetime.timedelta(days=prep_days)
        schedule.append({
            "action": "CLEAN & PREP",
            "supplier": "Internal",
            "material": "All collected materials",
            "quantity_kg": total_kg,
            "recommended_date": str(clean_date),
            "days_before_festival": prep_days,
        })
        schedule.append({
            "action": "DELIVER & INSTALL",
            "supplier": "Internal",
            "material": "All prepared materials",
            "quantity_kg": total_kg,
            "recommended_date": str(festival_date - datetime.timedelta(days=1)),
            "days_before_festival": 1,
        })

        return sorted(schedule, key=lambda x: x["recommended_date"])
