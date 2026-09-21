"""Regression for campsite-first loop recovery.

The recovery must not depend on generating more ORS round-trip seeds. It should
choose real campsites from one broad pool, solve the overnight order with a real
walking matrix, then request one final route.
"""
from pathlib import Path
from types import SimpleNamespace
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_campsite_loop_v9 as recovery


START = {"name": "Mont Saint-Michel", "lat": 48.636, "lon": -1.511, "category": "place"}
CAMPS = [
    {"name": "Camping A", "lat": 48.67, "lon": -1.33, "category": "camping", "source_url": "a"},
    {"name": "Camping B", "lat": 48.80, "lon": -1.50, "category": "camping", "source_url": "b"},
    {"name": "Camping C", "lat": 48.68, "lon": -1.70, "category": "camping", "source_url": "c"},
    {"name": "Camping mauvais", "lat": 48.64, "lon": -1.40, "category": "camping", "source_url": "bad"},
]


def hav(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


class V3:
    @staticmethod
    def _parse_intent(data):
        return {
            "route_type": "Boucle",
            "accommodation": "camping",
            "days": 4,
            "daily_target": 18.0,
            "daily_min": 13.0,
            "daily_max": 23.0,
            "total_target": 72.0,
            "difficulty": "medium",
        }

    @staticmethod
    def _fold(value):
        return str(value or "").casefold()

    @staticmethod
    def _location(data):
        return "Mont Saint-Michel"

    @staticmethod
    def _geocode(query):
        return [dict(START)]

    @staticmethod
    def _dist(a, b):
        return hav(a, b)

    @staticmethod
    def _stage_distances(coords, boundaries, legacy_main, total):
        assert len(boundaries) == 5
        assert boundaries[0]["name"] == "Mont Saint-Michel"
        assert boundaries[-1]["name"] == "Mont Saint-Michel"
        assert {x["name"] for x in boundaries[1:-1]} == {"Camping A", "Camping B", "Camping C"}
        return [17.0, 19.0, 18.0, 18.0]


class Roundtrip:
    nearby_calls = 0

    @staticmethod
    def _haversine(a, b):
        aa = {"lat": a[0], "lon": a[1]}
        bb = {"lat": b[0], "lon": b[1]}
        return hav(aa, bb)

    @classmethod
    def _nearby_stays(cls, v3, anchor, category, radius_km):
        cls.nearby_calls += 1
        assert category == "camping"
        assert radius_km >= 18
        return [dict(x) for x in CAMPS]

    @staticmethod
    def _roundtrip_request(*args, **kwargs):
        raise AssertionError("Camping-first recovery must not request another ORS round-trip seed")


class ORS:
    ORS_PROFILE = "foot-hiking"
    matrix_calls = 0
    route_calls = 0

    @classmethod
    def get_distance_matrix(cls, coords):
        cls.matrix_calls += 1
        # indexes: 0 start, 1 A, 2 B, 3 C, 4 bad.  The valid cycle can be
        # traversed clockwise or anti-clockwise; both are correct.
        return {
            "fallback": False,
            "distances": [
                [0, 17, 31, 18, 8],
                [17, 0, 19, 30, 9],
                [31, 19, 0, 18, 27],
                [18, 30, 18, 0, 26],
                [8, 9, 27, 26, 0],
            ],
        }

    @classmethod
    def get_route(cls, coords, distance_gps):
        cls.route_calls += 1
        assert len(coords) == 5
        return {
            "coords": coords,
            "distance": 72.0,
            "fallback": False,
            "profile": "foot-hiking",
        }


legacy = SimpleNamespace(
    distance_gps=lambda coords: 72.0,
    elevation_gain=lambda coords: 420,
)
data = SimpleNamespace(
    days=4,
    daily_km=18,
    difficulty="medium",
    require_water=False,
    require_transit=False,
)

result = recovery._recover(data, legacy, V3, Roundtrip, ORS)
assert Roundtrip.nearby_calls == 1, Roundtrip.nearby_calls
assert ORS.matrix_calls == 1, ORS.matrix_calls
assert ORS.route_calls == 1, ORS.route_calls
assert result["planner_fallback"] == "ors-camping-matrix-loop"
assert result["route_preview"]["fallback"] is False
assert len(result["stages"]) == 4
overnight = [x["overnight"] for x in result["stages"][:3]]
assert set(overnight) == {"Camping A", "Camping B", "Camping C"}, overnight
assert "Camping mauvais" not in overnight
assert max(x["distance_km"] for x in result["stages"]) <= 23.35
print("Campsite-first matrix loop recovery: OK")
