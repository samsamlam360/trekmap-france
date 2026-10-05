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

# The relation-detail endpoint exposes the provider's full route-builder tree.
# Parse its ordered Web-Mercator BaseWays instead of reconstructing a long loop
# from bbox-clipped /list/segments fragments.
full_ring = rectangle_loop()
quarter = max(2, (len(full_ring) - 1) // 4)
ring_parts = [
    full_ring[0:quarter + 1],
    full_ring[quarter:2 * quarter + 1],
    full_ring[2 * quarter:3 * quarter + 1],
    full_ring[3 * quarter:],
]

def mercator_line(points, ident):
    coords = []
    for lat, lon in points:
        x, y = gr_module._lonlat_to_mercator(lon, lat)
        coords.append([x, y])
    return {
        "route_type": "base",
        "start": 0,
        "id": ident,
        "tags": {},
        "length": 1,
        "direction": 0,
        "role": "",
        "geometry": {"type": "LineString", "coordinates": coords},
    }

full_route_tree = {
    "route_type": "route",
    "length": 80000,
    "linear": "yes",
    "start": 0,
    "main": [
        {
            "route_type": "linear",
            "start": 0,
            "length": 20000,
            "ways": [mercator_line(part, 100 + i)],
        }
        for i, part in enumerate(ring_parts)
    ],
    "appendices": [],
}
detail_lines = gr_module._waymarked_route_lines(full_route_tree)
detail_coords = gr_module._join_ordered_waymarked_lines(detail_lines)
assert len(detail_lines) == 4, len(detail_lines)
assert len(detail_coords) > 100, len(detail_coords)
assert rescue._dist(detail_coords[0], detail_coords[-1]) < 0.05, (
    detail_coords[0], detail_coords[-1]
)

# A clipped Waymarked candidate may look open even though its authoritative
# full relation is closed. Hydrate only that candidate, then select the real
# hiking loop without asking a generic round-trip router to invent one.
clipped = {
    "id": 580058,
    "name": "Tour de test",
    "ref": "GR 58",
    "network": "rwn",
    "coords": full_ring[:190],
    "length_km": rescue._length(full_ring[:190]),
    "source_url": "https://www.openstreetmap.org/relation/580058",
    "confidence": "high-route-evidence-secondary",
    "discovery_provider": "Waymarked Trails (OpenStreetMap-derived)",
}
hydrated = {
    **clipped,
    "coords": full_ring,
    "length_km": rescue._length(full_ring),
    "confidence": "high-route-evidence-secondary-full",
}
hydrate_calls = []
fake_gr_full = SimpleNamespace(
    _discover=lambda *_args: [],
    _discover_generic=lambda *_args: [],
    _discover_waymarked=lambda *_args: [clipped],
    _hydrate_waymarked_relation=lambda candidate: (
        hydrate_calls.append(candidate["id"]) or dict(hydrated)
    ),
)
full_start = {
    "name": "Départ test",
    "lat": full_ring[0][0],
    "lon": full_ring[0][1],
    "category": "place",
}
full_target = rescue._length(full_ring)
full_route, full_warning = rescue._relation_loop(
    v3, fake_gr_full, full_start, full_target
)
assert full_warning is None, full_warning
assert full_route is not None, full_route
assert full_route["routing_mode"] == "osm-hiking-relation-loop", full_route
assert full_route["relation_ref"] == "GR 58", full_route
assert rescue._dist(full_route["coords"][0], full_route["coords"][-1]) < 0.05
assert hydrate_calls == [580058], hydrate_calls

# Long regional loops may start on a real long-distance trail a little more
# than 12 km from the geocoded area centre, provided no explicit start/end/via
# constraint exists upstream. Short loops keep the historical 12 km ceiling.
assert rescue._section_start_offset_limit(80.0) == 12.0
assert 15.0 <= rescue._section_start_offset_limit(126.0) <= 15.2
assert rescue._section_start_offset_limit(300.0) == 18.0

# Synthetic ~100 km continuous ring. The requested regional anchor sits about
# 13 km outside its western edge, reproducing the Queyras-style 12.5 km miss.
ring_center_lat, ring_center_lon = 45.50, 6.80
ring_radius_km = 16.0
long_ring = []
for i in range(241):
    theta = math.pi + 2 * math.pi * i / 240
    long_ring.append([
        ring_center_lat + ring_radius_km * math.sin(theta) / 110.574,
        ring_center_lon + ring_radius_km * math.cos(theta) / (
            111.320 * math.cos(math.radians(ring_center_lat))
        ),
    ])
regional_start = {
    "name": "Centre régional",
    "lat": ring_center_lat,
    "lon": ring_center_lon - (ring_radius_km + 13.0) / (
        111.320 * math.cos(math.radians(ring_center_lat))
    ),
    "category": "place",
}
long_trail = {
    "id": 580058,
    "name": "Grand tour régional",
    "ref": "GR 58",
    "network": "rwn",
    "coords": long_ring,
    "length_km": rescue._length(long_ring),
}
_long_idx, long_off = rescue._nearest_index(long_ring, regional_start)
assert 12.0 < long_off < 14.0, long_off
long_rows = rescue._section_candidates([long_trail], regional_start, 126.0)
assert long_rows, (long_off, rescue._length(long_ring))
short_rows = rescue._section_candidates([long_trail], regional_start, 80.0)
assert short_rows == [], short_rows

# A transient cold-provider timeout must get exactly one shorter retry. This
# mirrors the production Crozon failure where the first Waymarked lookup missed
# but an identical benchmark immediately afterwards recovered GR 34.
original_waymarked_get = gr_module.requests.get
waymarked_http_calls = []

class FakeWaymarkedResponse:
    status_code = 200

    @staticmethod
    def raise_for_status():
        return None

    @staticmethod
    def json():
        return {"results": [{"id": 34, "ref": "GR 34"}]}

def flaky_waymarked_get(url, **kwargs):
    waymarked_http_calls.append((url, float(kwargs.get("timeout") or 0)))
    if len(waymarked_http_calls) == 1:
        raise gr_module.requests.Timeout("synthetic cold timeout")
    return FakeWaymarkedResponse()

gr_module.requests.get = flaky_waymarked_get
try:
    retry_payload = gr_module._waymarked_request(
        "/list/by_area",
        {"bbox": "0,0,1,1", "limit": 20},
        2.4,
    )
finally:
    gr_module.requests.get = original_waymarked_get

assert retry_payload["results"][0]["ref"] == "GR 34", retry_payload
assert len(waymarked_http_calls) == 2, waymarked_http_calls
assert waymarked_http_calls[1][1] < waymarked_http_calls[0][1], waymarked_http_calls

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

# Heavy relation discovery is reserved for requests where route evidence can
# materially improve the answer. Generic short loops must go straight to the
# bounded ORS path instead of paying Overpass + Waymarked cold latency.
assert not rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 2,
    "total_target": 32.0,
    "raw": "boucle de 2 jours autour du Hohneck, privilégier les sentiers",
}, 32.0, 2)
assert not rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 2,
    "total_target": 28.0,
    "raw": "boucle sportive autour de Gavarnie sur de vrais chemins pédestres",
}, 28.0, 2)

# Evidence-first remains active for coastal, explicitly named and long loops.
assert rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 3,
    "total_target": 54.0,
    "raw": "boucle sur la presqu ile de Crozon en restant sur des sentiers cotiers",
}, 54.0, 3)
assert rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 4,
    "total_target": 64.0,
    "raw": "je veux faire le Tour des Fiz en 4 jours sur l itineraire existant",
}, 64.0, 4)
assert rescue._named_relation_section_allowed({
    "route_type": "Boucle",
    "days": 4,
    "total_target": 64.0,
    "raw": "je veux faire le Tour des Fiz en 4 jours sur l itineraire existant",
}, 64.0, days_override=4, known_loop=True)
assert not rescue._named_relation_section_allowed({
    "route_type": "Boucle",
    "days": 4,
    "total_target": 64.0,
    "raw": "boucle de quatre jours autour du mont Lozere sur de beaux sentiers",
}, 64.0, days_override=4, known_loop=True)
assert rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 7,
    "total_target": 126.0,
    "raw": "itinerance dans le Queyras, privilegier un itineraire de grande randonnee coherent",
}, 126.0, 7)
assert rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 6,
    "total_target": 108.0,
    "raw": "trek de 6 jours dans le Beaufortain sur des itineraires existants",
}, 108.0, 6)
assert rescue._relation_first_allowed({
    "route_type": "Boucle",
    "days": 3,
    "total_target": 54.0,
    "raw": "boucle de 3 jours en suivant le GR 34",
}, 54.0, 3)

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
    "discovery_provider": "Waymarked Trails (OpenStreetMap-derived)",
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

secondary_waymarked_calls = []
def forbidden_secondary_waymarked(*_args, **_kwargs):
    secondary_waymarked_calls.append(1)
    return []

real_ors.get_distance_matrix = fake_matrix
real_ors.get_route = fake_closure
try:
    section_route, warning = rescue._relation_section_loop(
        v3,
        SimpleNamespace(_discover_waymarked=forbidden_secondary_waymarked),
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
assert secondary_waymarked_calls == [], secondary_waymarked_calls

# If Matrix is unavailable, the two exact Directions attempts must come from
# diverse relation-section families. Otherwise two neighbouring endpoints of
# the same arc can consume the whole fallback budget while a distinct valid
# closure sits immediately behind them.
def fallback_arc(center_lat):
    center_lon = 6.80
    radius_km = 22.5
    angle = 4.0
    out = []
    for i in range(121):
        theta = angle * i / 120
        out.append([
            center_lat + radius_km * math.sin(theta) / 110.574,
            center_lon + radius_km * math.cos(theta) / (
                111.320 * math.cos(math.radians(center_lat))
            ),
        ])
    return out

fallback_trail = {
    "id": 580058,
    "name": "Grand tour de secours",
    "ref": "GR 58",
    "network": "rwn",
}
fallback_sections = [
    fallback_arc(45.00),
    fallback_arc(45.35),
    fallback_arc(45.80),
]
fallback_rows = [
    (0.0, fallback_trail, fallback_sections[0], 3.0, 90.0, 1),
    (0.1, fallback_trail, fallback_sections[1], 3.0, 90.4, 1),
    (0.2, fallback_trail, fallback_sections[2], 3.0, 90.0, -1),
]

original_section_candidates = rescue._section_candidates
original_matrix_rank = rescue._matrix_rank_section_candidates
original_fallback_route = real_ors.get_route
fallback_closure_calls = []

def synthetic_sections(*_args, **_kwargs):
    return list(fallback_rows)

def unavailable_matrix(*_args, **_kwargs):
    return [], False, "OpenRouteService Matrix HTTP 500."

def selective_closure(points, _distance_gps):
    fallback_closure_calls.append(points)
    a, b = points
    # First diverse family fails; the second diverse direction succeeds.
    if float(a[0]) < 45.6:
        return {
            "coords": [],
            "distance": 0.0,
            "fallback": True,
            "warning": "synthetic first-family miss",
        }
    coords = []
    for i in range(31):
        t = i / 30
        coords.append([
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
        ])
    return {
        "coords": coords,
        "distance": rescue._length(coords),
        "fallback": False,
        "routing_mode": "fake-diverse-closure",
    }

rescue._section_candidates = synthetic_sections
rescue._matrix_rank_section_candidates = unavailable_matrix
real_ors.get_route = selective_closure
try:
    diverse_route, diverse_warning = rescue._relation_section_loop(
        SimpleNamespace(),
        SimpleNamespace(_discover_waymarked=lambda *_args: []),
        {"name": "Zone longue", "lat": 45.0, "lon": 6.8, "category": "place"},
        126.0,
        13.5,
        22.5,
        7,
        trails=[fallback_trail],
    )
finally:
    rescue._section_candidates = original_section_candidates
    rescue._matrix_rank_section_candidates = original_matrix_rank
    real_ors.get_route = original_fallback_route

assert diverse_warning is None, diverse_warning
assert diverse_route is not None, diverse_route
assert diverse_route["routing_mode"] == "osm-hiking-relation-section-loop", diverse_route
assert len(fallback_closure_calls) == 2, fallback_closure_calls
assert float(fallback_closure_calls[1][0][0]) > 45.6, fallback_closure_calls

# Non-closed / wildly discontinuous relations must never be promoted just to
# make an error disappear.
bad = dict(trail)
bad["coords"] = [[47.2, -3.3], [47.2, -3.2], [48.0, -2.0], [47.3, -3.1]]
gr_bad = SimpleNamespace(_discover=lambda _v3, _start, _radius: [bad])
route, warning = rescue._relation_loop(v3, gr_bad, dict(start), 80.0)
assert route is None
assert warning

# Dispatch contract: a named short tour may use already-discovered section
# evidence below the generic 90 km threshold, but only through the preloaded
# candidate gate (no unconditional extra provider wave).
import inspect
install_source = inspect.getsource(rescue.install_trail_loop_rescue)
assert "named_preloaded" in install_source, install_source
assert "_section_candidates(" in install_source, install_source
assert "generic_allowed or named_preloaded" in install_source, install_source

print("Closed GR loop rescue + compact campsite routing: OK")
