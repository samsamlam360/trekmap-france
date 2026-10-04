"""Regression tests for closed GR/GRP loop rescue."""
from pathlib import Path
from types import SimpleNamespace
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_trail_loop_rescue_v9 as rescue
from backend import trekbrain_gr_v9 as gr_module


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

# The secondary trail index returns clipped OSM relation geometry in Web
# Mercator. Parsing it must preserve the real relation id/ref and reconstruct
# WGS84 [lat, lon] geometry without involving the network in CI.
sample_wgs = [[48.20 + 0.006 * i, -4.72 + 0.020 * i] for i in range(21)]
sample_merc = []
for lat, lon in sample_wgs:
    x, y = gr_module._lonlat_to_mercator(lon, lat)
    sample_merc.append([x, y])
waymarked = gr_module._waymarked_trails_from_payloads(
    {
        "results": [
            {"type": "relation", "id": 340034, "ref": "GR 34", "name": "Sentier des douaniers"},
            {"type": "relation", "id": 99, "ref": "", "name": "Promenade locale"},
        ]
    },
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": 340034,
                "geometry": {"type": "LineString", "coordinates": sample_merc},
            }
        ],
    },
)
assert len(waymarked) == 1
assert waymarked[0]["id"] == 340034
assert waymarked[0]["ref"] == "GR 34"
assert waymarked[0]["length_km"] > 20
assert waymarked[0]["discovery_provider"].startswith("Waymarked Trails")
assert abs(waymarked[0]["coords"][0][0] - sample_wgs[0][0]) < 1e-5
assert abs(waymarked[0]["coords"][0][1] - sample_wgs[0][1]) < 1e-5

# A long open coastal relation can be used as the real backbone of a loop:
# follow the mapped trail, then close only the final return through a pedestrian
# router. This is the generic Crozon-style case the closed-relation rescue could
# not solve.
assert rescue._coastal_section_allowed({
    "route_type": "Boucle",
    "days": 3,
    "total_target": 47.0,
    "raw": "boucle de trois jours en restant au maximum sur des sentiers côtiers",
}, 47.0)
assert not rescue._coastal_section_allowed({
    "route_type": "Boucle",
    "days": 3,
    "total_target": 47.0,
    "raw": "boucle tranquille en forêt",
}, 47.0)

lat0, lon0, radius_km = 48.25, -4.50, 9.3
open_coast = []
for i in range(121):
    theta = math.pi - math.pi * i / 120
    x = radius_km * math.cos(theta)
    y = radius_km * math.sin(theta)
    open_coast.append([
        lat0 + y / 110.574,
        lon0 + x / (111.320 * math.cos(math.radians(lat0))),
    ])

open_trail = {
    "id": 34,
    "name": "Sentier côtier de test",
    "ref": "GR 34",
    "network": "nwn",
    "coords": open_coast,
    "length_km": rescue._length(open_coast),
    "source_url": "https://www.openstreetmap.org/relation/34",
}
open_start = {
    "name": "Presqu'île de test",
    "lat": open_coast[0][0],
    "lon": open_coast[0][1],
    "category": "place",
}

from backend import ors as real_ors
original_get_route = real_ors.get_route
original_get_distance_matrix = real_ors.get_distance_matrix
closure_calls = []
matrix_calls = []

def fake_matrix(coords):
    matrix_calls.append(coords)
    matrix = []
    for a in coords:
        matrix.append([round(rescue._dist(a, b), 3) for b in coords])
    return {"distances": matrix, "fallback": False, "routing_mode": "fake-matrix"}


def fake_closure(points, _distance_gps):
    closure_calls.append(points)
    a, b = points
    coords = []
    for i in range(25):
        t = i / 24
        coords.append([
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
        ])
    return {
        "coords": coords,
        "distance": rescue._length(coords),
        "fallback": False,
        "routing_mode": "fake-pedestrian-closure",
    }

real_ors.get_distance_matrix = fake_matrix
real_ors.get_route = fake_closure
try:
    section_route, warning = rescue._relation_section_loop(
        v3,
        SimpleNamespace(_discover=lambda *_args: [open_trail]),
        open_start,
        47.0,
        11.75,
        19.6,
        3,
        trails=[open_trail],
    )
finally:
    real_ors.get_route = original_get_route
    real_ors.get_distance_matrix = original_get_distance_matrix

assert warning is None, warning
assert section_route is not None
assert section_route["fallback"] is False
assert section_route["routing_mode"] == "osm-hiking-relation-section-loop"
assert section_route["relation_ref"] == "GR 34"
assert 38.5 <= section_route["distance"] <= 55.5
assert section_route["relation_share"] >= 0.58
assert section_route["closure_share"] <= 0.42
assert rescue._dist(section_route["coords"][0], section_route["coords"][-1]) <= 0.12
assert len(matrix_calls) == 1
assert len(matrix_calls[0]) <= 16
assert 1 <= len(closure_calls) <= 2

# Non-closed / wildly discontinuous relations must never be promoted just to
# make an error disappear.
bad = dict(trail)
bad["coords"] = [[47.2, -3.3], [47.2, -3.2], [48.0, -2.0], [47.3, -3.1]]
gr_bad = SimpleNamespace(_discover=lambda _v3, _start, _radius: [bad])
route, warning = rescue._relation_loop(v3, gr_bad, dict(start), 80.0)
assert route is None
assert warning

print("Closed GR loop rescue + compact campsite routing: OK")
