"""Regression for campsite-aware ORS loop recovery."""
from types import SimpleNamespace

from backend import trekbrain_campsite_loop_v9 as recovery


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
        return [{"name": "Mont Saint-Michel", "lat": 48.636, "lon": -1.511}]

    @staticmethod
    def _stage_distances(coords, boundaries, legacy_main, total):
        assert len(boundaries) == 5
        return [17.0, 19.0, 18.0, 18.0]


class Roundtrip:
    seeds = []

    @classmethod
    def _roundtrip_request(cls, start, target_km, seed):
        cls.seeds.append(seed)
        coords = [[48.636, -1.511], [48.70, -1.40], [48.78, -1.51], [48.70, -1.62], [48.636, -1.511]]
        return {"coords": coords, "distance": 72.0, "fallback": False, "profile": "foot-hiking"}, None

    @staticmethod
    def _balanced_corridor_stays(v3, coords, days, category, daily_target, daily_min, daily_max):
        seed = Roundtrip.seeds[-1]
        if seed == 29:
            return [], {"options": [3, 0], "search_radius_km": 4.0, "window_km": 7.2}
        camps = [
            {"name": "Camping A", "lat": 48.68, "lon": -1.43, "category": "camping"},
            {"name": "Camping B", "lat": 48.76, "lon": -1.52, "category": "camping"},
            {"name": "Camping C", "lat": 48.69, "lon": -1.60, "category": "camping"},
        ]
        return camps, {"options": [2, 3, 2], "search_radius_km": 4.0, "window_km": 7.2}

    @staticmethod
    def _route_points_with_stays(coords, start, stays, days):
        return [start] + stays + [start]


class ORS:
    ORS_PROFILE = "foot-hiking"

    @staticmethod
    def get_route(coords, distance_gps):
        return {
            "coords": [[48.636, -1.511], [48.68, -1.43], [48.76, -1.52], [48.69, -1.60], [48.636, -1.511]],
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

Roundtrip.seeds.clear()
result = recovery._recover(data, legacy, V3, Roundtrip, ORS)
assert Roundtrip.seeds == [29, 47], Roundtrip.seeds
assert result["planner_fallback"] == "ors-campsite-aware-round-trip"
assert result["route_preview"]["fallback"] is False
assert len(result["stages"]) == 4
assert len(result["accommodations"]) == 3
assert [x["overnight"] for x in result["stages"][:3]] == ["Camping A", "Camping B", "Camping C"]
assert max(x["distance_km"] for x in result["stages"]) <= 23.35
print("Campsite-aware alternate ORS loop recovery: OK")
