"""Regression: Belle-Ile must use GR 340 directly for 18 and 22 km/day requests."""
from types import SimpleNamespace

from backend import trekbrain_belle_ile_canonical_v9 as canonical


class FakeData:
    prompt = "Je veux faire le tour de Belle-Île en 5 jours"
    region = "Belle-Île-en-Mer"
    days = 5
    daily_km = 18
    difficulty = "medium"


class FakeV3:
    def __init__(self, daily):
        self.daily = daily

    def _parse_intent(self, data):
        return {
            "route_type": "Boucle",
            "days": 5,
            "daily_target": float(self.daily),
            "daily_min": 13.5 if self.daily == 18 else 16.5,
            "daily_max": 22.5 if self.daily == 18 else 27.5,
            "total_target": float(self.daily) * 5,
            "accommodation": "balanced",
            "difficulty": "medium",
        }

    @staticmethod
    def _fold(value):
        return str(value).casefold()

    @staticmethod
    def _location(data):
        return "Belle-Île-en-Mer"

    @staticmethod
    def _geocode(query):
        return [{"name": "Belle-Île-en-Mer", "lat": 47.33, "lon": -3.18}]

    @staticmethod
    def _stage_distances(coords, boundaries, legacy, total):
        return [float(total) / 5.0] * 5


class FakeBelle:
    @staticmethod
    def _is_belle_ile(point):
        return 47.20 <= float(point["lat"]) <= 47.44 and -3.40 <= float(point["lon"]) <= -2.95

    @staticmethod
    def _targeted_gr340(v3, gr, rescue, start, target_km):
        # Synthetic closed relation; the requested target may be 90 or 110 km,
        # but the canonical real-world route remains the same backbone.
        coords = [
            [47.33, -3.18], [47.38, -3.10], [47.36, -3.02], [47.29, -3.00],
            [47.23, -3.08], [47.22, -3.20], [47.27, -3.30], [47.34, -3.29],
            [47.33, -3.18],
        ]
        start["lat"], start["lon"] = coords[0]
        start["name"] = "Départ sur GR 340"
        start["category"] = "trail"
        return {
            "coords": coords,
            "distance": 90.0,
            "fallback": False,
            "routing_mode": "osm-hiking-relation-loop",
            "profile": "hiking-relation",
            "provider": "OpenStreetMap hiking relation",
            "relation_ref": "GR 340",
            "relation_name": "Tour de Belle-Île-en-Mer",
            "relation_source_url": "https://www.openstreetmap.org/relation/6850120",
            "relation_geometry": True,
        }, None


class FakeRoundtrip:
    @staticmethod
    def _equal_anchors(coords, days):
        indices = [1, 3, 5, 7]
        return [
            {"name": f"Repère jour {i+1}", "lat": coords[idx][0], "lon": coords[idx][1], "category": "route_anchor"}
            for i, idx in enumerate(indices)
        ]

    @staticmethod
    def _balanced_corridor_stays(*args, **kwargs):
        raise AssertionError("No accommodation search expected in this regression")


class NoORS:
    @staticmethod
    def get_route(*args, **kwargs):
        raise AssertionError("Belle-Ile canonical route must not ask ORS to rebuild the full loop")


class FakeLegacy:
    @staticmethod
    def distance_gps(coords):
        return 1.0

    @staticmethod
    def elevation_gain(coords):
        return 600


for daily in (18, 22):
    data = FakeData()
    data.daily_km = daily
    result = canonical._build_canonical(
        data,
        FakeLegacy(),
        FakeV3(daily),
        object(),
        object(),
        FakeRoundtrip(),
        object(),
        NoORS(),
        FakeBelle(),
    )
    assert result["canonical_route"] is True
    assert result["route_type"] == "Boucle"
    assert result["route_preview"]["relation_ref"] == "GR 340"
    assert result["route_preview"]["fallback"] is False
    assert result["distance_km"] == 90.0
    assert len(result["stages"]) == 5

print("Belle-Ile canonical GR 340 planner (18/22 km-day): OK")
