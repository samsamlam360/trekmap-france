"""Regression for campsite-aware ORS round-trip recovery."""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_roundtrip_v9 as roundtrip


# Build an approximately 72 km synthetic corridor. The three campsites sit
# around 1.5 km off the corridor and about 3 km before each mathematically exact
# 18 km split. The old exact-anchor lookup therefore misses them, even though
# they produce sensible day lengths once the stage boundaries are allowed to move.
lat = 48.60
km_per_lon_degree = 111.32 * math.cos(math.radians(lat))
lon_step = 1.0 / km_per_lon_degree
coords = [[lat, -1.80 + i * lon_step] for i in range(73)]

north_offset = 1.5 / 111.32
camp_indices = (15, 33, 51)
camps = [
    {
        "name": f"Camping test {n}",
        "lat": coords[idx][0] + north_offset,
        "lon": coords[idx][1],
        "category": "camping",
        "source_url": f"https://www.openstreetmap.org/node/{1000+n}",
    }
    for n, idx in enumerate(camp_indices, start=1)
]


class CorridorV3:
    @staticmethod
    def _nearby(lat, lon, radius, categories):
        if "camping" not in categories:
            return []
        center = [lat, lon]
        return [
            dict(camp)
            for camp in camps
            if roundtrip._haversine(center, [camp["lat"], camp["lon"]]) <= radius
        ]

    @staticmethod
    def _dist(a, b):
        return roundtrip._haversine([a["lat"], a["lon"]], [b["lat"], b["lon"]])


anchors = roundtrip._equal_anchors(coords, 4)
assert len(anchors) == 3, anchors

# Reproduce the production failure shown on mobile: no camping is found by
# looking only within 2.6 km of the exact mathematical endpoints.
legacy = roundtrip._nearest_unique_stays(CorridorV3, anchors, "camping", 2.6)
assert legacy == [], legacy

chosen, meta = roundtrip._balanced_corridor_stays(
    CorridorV3,
    coords,
    days=4,
    category="camping",
    daily_target=18.0,
    daily_min=13.5,
    daily_max=22.5,
)
assert len(chosen) == 3, (chosen, meta)
assert [x["name"] for x in chosen] == [x["name"] for x in camps], (chosen, meta)
assert all(float(x["_offroute_km"]) < 2.0 for x in chosen), chosen
assert float(meta["search_radius_km"]) >= 3.6, meta

start = {"name": "Départ", "lat": coords[0][0], "lon": coords[0][1], "category": "place"}
route_points = roundtrip._route_points_with_stays(coords, start, chosen, 4)
route_names = [str(x.get("name") or "") for x in route_points]
for camp in camps:
    assert camp["name"] in route_names, route_names
assert route_points[0]["name"] == "Départ"
assert route_points[-1]["name"] == "Départ"
assert sum(1 for x in route_points if x.get("category") == "route_anchor") >= 8, route_points

print("Adaptive campsite corridor recovery: OK")
