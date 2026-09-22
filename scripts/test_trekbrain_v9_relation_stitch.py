"""Regression: a real GR loop must stay continuous when campsite detours are added."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_relation_stitch_v9 as stitch


def dense_rectangle():
    south, north = 47.22, 47.38
    west, east = -3.32, -3.08
    coords = []
    steps = 80
    for i in range(steps):
        t = i / steps
        coords.append([south, west + (east - west) * t])
    for i in range(steps):
        t = i / steps
        coords.append([south + (north - south) * t, east])
    for i in range(steps):
        t = i / steps
        coords.append([north, east - (east - west) * t])
    for i in range(steps):
        t = i / steps
        coords.append([north - (north - south) * t, west])
    coords.append(list(coords[0]))
    return coords


base = dense_rectangle()
relation = {
    "coords": base,
    "distance": stitch._length(base),
    "fallback": False,
    "routing_mode": "osm-hiking-relation-loop",
    "relation_geometry": True,
    "relation_ref": "GR 340",
    "relation_name": "Tour de Belle-Île-en-Mer",
    "relation_source_url": "https://www.openstreetmap.org/relation/6850120",
}

# Four nights slightly off the GR. Each local request is deliberately returned
# as a dense anchor -> stay -> anchor path, proving the main loop itself never
# needs to be re-routed through sparse island-wide waypoints.
stays = []
for idx, offset in ((70, 0.010), (150, -0.010), (240, 0.010), (300, -0.008)):
    anchor = base[idx]
    stays.append({
        "name": f"Camping {idx}",
        "category": "camping",
        "lat": anchor[0] + offset,
        "lon": anchor[1],
        "_route_index": idx,
    })

calls = []

class FakeORS:
    @staticmethod
    def get_route(points, _distance_gps):
        calls.append(points)
        a, stay, _a2 = points
        coords = []
        for n in range(5):
            t = n / 4
            coords.append([a[0] + (stay[0] - a[0]) * t, a[1] + (stay[1] - a[1]) * t])
        for n in range(1, 5):
            t = n / 4
            coords.append([stay[0] + (a[0] - stay[0]) * t, stay[1] + (a[1] - stay[1]) * t])
        return {
            "coords": coords,
            "distance": stitch._length(coords),
            "fallback": False,
            "routing_mode": "fake-pedestrian",
        }

legacy = SimpleNamespace(distance_gps=lambda coords: stitch._length(coords))
route, warning = stitch._stitch_relation_with_stays(relation, stays, FakeORS, legacy)
assert warning is None, warning
assert route is not None
assert route["fallback"] is False
assert route["routing_mode"] == "osm-hiking-relation-loop-with-routed-stays"
assert route["relation_ref"] == "GR 340"
assert stitch._max_gap(route["coords"]) < 0.55
assert len(calls) == 4, len(calls)
assert all(len(call) == 3 for call in calls)
assert route["coords"][0] == route["coords"][-1]

# Reproduce the production symptom: a secondary router returns one connector
# with a multi-kilometre jump. It must be rejected here, before final safety sees
# a mysterious 5.8 km discontinuity.
class BrokenORS:
    @staticmethod
    def get_route(points, _distance_gps):
        a, stay, _a2 = points
        return {
            "coords": [list(a), [a[0] + 0.055, a[1]], list(stay), list(a)],
            "distance": 8.0,
            "fallback": False,
            "routing_mode": "broken-secondary",
        }

broken, warning = stitch._stitch_relation_with_stays(relation, stays[:1], BrokenORS, legacy)
assert broken is None
assert warning and "discontinu" in warning.casefold(), warning

print("GR relation backbone + local campsite connector regression: OK")
