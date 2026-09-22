"""Regression tests for Matrix HTTP 500 and >100 km loop recovery."""
from pathlib import Path
import math
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from backend import trekbrain_matrix_rescue_v9 as rescue


START = {"name": "Départ", "lat": 48.63, "lon": -1.51, "category": "place"}
STAYS = [
    {"name": "Camping A", "lat": 48.69, "lon": -1.39, "category": "camping", "source_url": "a"},
    {"name": "Camping B", "lat": 48.77, "lon": -1.51, "category": "camping", "source_url": "b"},
    {"name": "Camping C", "lat": 48.68, "lon": -1.66, "category": "camping", "source_url": "c"},
    {"name": "Camping D", "lat": 48.57, "lon": -1.64, "category": "camping", "source_url": "d"},
]


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def original_recover(*args, **kwargs):
    raise HTTPException(status_code=503, detail="OpenRouteService Matrix HTTP 500.")


def original_best(start, target_km, daily_min, daily_max, days, v3):
    if target_km > 99:
        raise HTTPException(status_code=422, detail="old 100 km limit")
    return {"marker": "original", "distance": target_km}


roundtrip_calls = []


def roundtrip_request(start, target_km, seed):
    roundtrip_calls.append((target_km, seed))
    mid = [float(start["lat"]) + 0.02 + (seed % 3) * 0.002, float(start["lon"]) + 0.03]
    return {
        "coords": [[float(start["lat"]), float(start["lon"])], mid, [float(start["lat"]), float(start["lon"])]],
        "distance": float(target_km),
        "fallback": False,
        "profile": "foot-hiking",
    }, None


roundtrip = SimpleNamespace(
    _best_roundtrip=original_best,
    _roundtrip_request=roundtrip_request,
    _haversine=haversine,
    ors=SimpleNamespace(ORS_PROFILE="foot-hiking"),
)


def render_result(data, legacy, v3, ors, intent, location, start, route, stays, stage_distances):
    return {
        "route_preview": {"routing_mode": route.get("routing_mode"), "coords": route.get("coords") or []},
        "advisor_notes": [],
        "confidence": {"limitations": []},
        "accommodations": list(stays),
        "stages": [{"distance_km": x} for x in stage_distances],
    }


camp = SimpleNamespace(
    _recover=original_recover,
    _start_for=lambda v3, location: dict(START),
    _diverse_stays=lambda v3, rt, start, category, days, target: [dict(x) for x in STAYS],
    _shape_ratio=lambda start, selected: 0.012,
    _render_result=render_result,
)


class V3:
    @staticmethod
    def _parse_intent(data):
        return {
            "route_type": "Boucle", "accommodation": "camping", "days": 4,
            "daily_target": 18.0, "daily_min": 13.5, "daily_max": 25.0,
        }

    @staticmethod
    def _fold(value):
        return str(value).casefold()

    @staticmethod
    def _location(data):
        return "Mont Saint-Michel"

    @staticmethod
    def _stage_distances(coords, boundaries, legacy, distance):
        # Deliberately allow a short first day, matching the real use case.
        return [9.0, 19.0, 20.0, 18.0]


class Legacy:
    @staticmethod
    def distance_gps(coords):
        return 66.0

    @staticmethod
    def elevation_gain(coords):
        return 0


class ORS:
    ORS_PROFILE = "foot-hiking"

    @staticmethod
    def get_route(coords, distance_gps):
        return {
            "coords": [list(x) for x in coords],
            "distance": 66.0,
            "fallback": False,
            "routing_mode": "ors",
            "profile": "foot-hiking",
        }


DATA = SimpleNamespace(days=4, daily_km=18.0, difficulty="medium", require_transit=False, require_water=False)

rescue._INSTALLED = False
rescue.install_matrix_resilience(camp, roundtrip)

# Matrix 500 must no longer be fatal when Directions can validate a campsite cycle.
result = camp._recover(DATA, Legacy, V3, roundtrip, ORS)
assert result["planner_fallback"] == "ors-camping-directions-loop", result
assert [x["distance_km"] for x in result["stages"]] == [9.0, 19.0, 20.0, 18.0]
assert len(result["accommodations"]) == 3
assert "Matrix" in result["confidence"]["limitations"][0]

# <=99 km keeps the existing fast path.
small = roundtrip._best_roundtrip(START, 80.0, 15.0, 25.0, 4, V3)
assert small.get("marker") == "original", small

# >100 km is split into several validated ORS round-trip lobes instead of failing.
long_route = roundtrip._best_roundtrip(START, 135.0, 15.0, 25.0, 6, V3)
assert long_route["fallback"] is False
assert long_route["routing_mode"] == "ors-round-trip-multilobe"
assert long_route["round_trip_lobes"] == 2
assert 130.0 <= long_route["distance"] <= 140.0, long_route
assert len(roundtrip_calls) >= 2

print("Matrix HTTP 500 + long-loop resilience: OK")
