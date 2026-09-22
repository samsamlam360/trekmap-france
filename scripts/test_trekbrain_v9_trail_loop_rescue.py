"""Regression tests for closed GR/GRP loop rescue."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_trail_loop_rescue_v9 as rescue


def rectangle_loop():
    """Dense ~75-85 km synthetic coastal-style loop around one island."""
    south, north = 47.22, 47.39
    west, east = -3.34, -3.08
    out = []
    steps = 70
    for i in range(steps):
        t = i / steps
        out.append([south, west + (east - west) * t])
    for i in range(steps):
        t = i / steps
        out.append([south + (north - south) * t, east])
    for i in range(steps):
        t = i / steps
        out.append([north, east - (east - west) * t])
    for i in range(steps):
        t = i / steps
        out.append([north - (north - south) * t, west])
    out.append(list(out[0]))
    return out


trail = {
    "id": 340,
    "name": "Tour côtier de Belle-Île",
    "ref": "GR 340",
    "network": "nwn",
    "coords": rectangle_loop(),
    "source_url": "https://www.openstreetmap.org/relation/340",
}
gr = SimpleNamespace(_discover=lambda _v3, _start, _radius: [trail])
v3 = SimpleNamespace()
start = {"name": "Belle-Île-en-Mer", "lat": 47.305, "lon": -3.21, "category": "place"}
route, warning = rescue._relation_loop(v3, gr, start, 80.0)
assert warning is None, warning
assert route is not None
assert route["fallback"] is False
assert route["routing_mode"] == "osm-hiking-relation-loop"
assert route["relation_ref"] == "GR 340"
assert route["coords"][0] == route["coords"][-1]
assert route["distance"] > 55
assert "GR 340" in start["name"]
assert rescue._dist([start["lat"], start["lon"]], route["coords"][0]) < 0.01

# A 5-day loop with four campsite detours can exceed the secondary router's
# sensible waypoint budget. Keep every campsite and its neighbouring junctions,
# then thin only redundant relation anchors.
points = [{"name": "Départ", "category": "trail", "lat": 47.2, "lon": -3.2}]
for i in range(28):
    points.append({"name": f"Repère {i}", "category": "route_anchor", "lat": 47.2 + i * 0.001, "lon": -3.2})
    if i in {4, 10, 16, 22}:
        points.append({"name": f"Camping {i}", "category": "camping", "lat": 47.2 + i * 0.001, "lon": -3.19})
        points.append({"name": f"Retour {i}", "category": "route_anchor", "lat": 47.2 + i * 0.001, "lon": -3.2})
points.append({"name": "Arrivée", "category": "trail", "lat": 47.2, "lon": -3.2})
compact = rescue._compact_route_points(points)
assert len(compact) <= 21, len(compact)
assert sum(1 for p in compact if p.get("category") == "camping") == 4
assert compact[0]["name"] == "Départ"
assert compact[-1]["name"] == "Arrivée"

# Non-closed / wildly discontinuous relations must never be promoted just to
# make an error disappear.
bad = dict(trail)
bad["coords"] = [[47.2, -3.3], [47.2, -3.2], [48.0, -2.0], [47.3, -3.1]]
gr_bad = SimpleNamespace(_discover=lambda _v3, _start, _radius: [bad])
route, warning = rescue._relation_loop(v3, gr_bad, dict(start), 80.0)
assert route is None
assert warning

print("Closed GR loop rescue + compact campsite routing: OK")
