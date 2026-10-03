"""Regression tests for TrekBrain v9 interactive latency controls."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import free_planner_v2 as free
from backend import ors
from backend import smart_planner_v3 as v3
from backend import smart_planner_v5 as v5
from backend import smart_planner_v9 as v9
from backend import trekbrain_roundtrip_v9 as roundtrip
from backend import trekbrain_route_logistics_v9 as logistics
from backend import trekbrain_speed_v9 as speed

# This test validates the default interactive profile, not an operator override.
os.environ.pop("TREKBRAIN_RETRY_BUDGET_SECONDS", None)
os.environ.pop("TREKBRAIN_OVERPASS_BUDGET_SECONDS", None)
os.environ.pop("TREKBRAIN_ORS_TIMEOUT_SECONDS", None)
os.environ.pop("TREKBRAIN_MATRIX_TIMEOUT_SECONDS", None)

speed._INSTALLED = False
speed._STAY_POOLS.clear()
speed.install_fast_planning(v3, v5, v9)

# The fast wrapper must stay signature-compatible with v5 candidate prompt
# generation, including TrekBrain's isolated internal strategy hint.
assert speed.FAST_PLANNING_WRAPPER_VERSION == 3
prompt_rows = v5._candidate_prompts(
    "boucle 2 jours 16 km par jour avec hebergement",
    [],
    {},
    "logistique ; campings ou refuges comme préférence interne",
)
assert prompt_rows and "Priorité interne TrekBrain" in prompt_rows[0], prompt_rows

# Explicit point-to-point requests with authoritative endpoints should route
# only the strongest candidate family. The validated route-split recovery handles
# day boundaries, so a second ORS lookalike only adds latency.
class DummyCandidate:
    def __init__(self, strategy):
        self.strategy = strategy

traverse_rows = [
    DummyCandidate("balanced-gr-corridor"),
    DummyCandidate("balanced-generic"),
    DummyCandidate("balanced-extra"),
]
pruned_traverse = speed._prune_route_candidates(
    traverse_rows,
    {
        "route_type": "Traversée",
        "start_query": "Tours",
        "end_query": "Chinon",
        "accommodation": "balanced",
    },
)
assert len(pruned_traverse) == 1, [x.strategy for x in pruned_traverse]

# Do not apply the same shortcut to an implicit non-loop request; without
# explicit endpoints the second family may materially change the route.
implicit_rows = speed._prune_route_candidates(
    traverse_rows,
    {"route_type": "Traversée", "start_query": "", "end_query": "", "accommodation": "balanced"},
)
assert 1 <= len(implicit_rows) <= 2, [x.strategy for x in implicit_rows]

# A second complete geographic hypothesis is not part of the default interactive
# path. The lower layers already compare route candidates.
assert v9.seconds("TREKBRAIN_RETRY_BUDGET_SECONDS", 10) == 0.0

# Photon fallback must preserve the exact serial query set and deterministic
# result order even though independent requests are now executed concurrently.
real_photon = free._geocode_photon
photon_queries = []

def fake_photon(query):
    photon_queries.append(query)
    # Return one unique nearby result per query. Deliberately vary completion
    # order so the collector has to restore historical deterministic ordering.
    import time as _time
    delay = 0.012 if "camping" in query else 0.004 if "refuge" in query else 0.001
    _time.sleep(delay)
    index = len(query)
    return [{
        "name": query,
        "short_name": query,
        "lat": 48.0 + (index % 5) * 0.001,
        "lon": 2.0 + (sum(ord(c) for c in query) % 7) * 0.001,
        "category": "place",
        "source_url": "placeholder",
    }]

free._geocode_photon = fake_photon
try:
    photon_rows = free._photon_category_candidates(
        "TestZone",
        {"lat": 48.0, "lon": 2.0},
        ["camping", "refuge", "food", "transit", "viewpoint", "water"],
    )
finally:
    free._geocode_photon = real_photon

expected_queries = [
    "camping TestZone",
    "refuge TestZone",
    "gîte TestZone",
    "boulangerie TestZone",
    "supermarché TestZone",
    "gare TestZone",
    "sommet TestZone",
    "belvédère TestZone",
]
assert sorted(photon_queries) == sorted(expected_queries), photon_queries
expected_categories = [
    "camping", "refuge", "refuge", "food", "food", "transit", "viewpoint", "viewpoint",
]
assert [row.get("category") for row in photon_rows] == expected_categories, photon_rows
assert [row.get("name") for row in photon_rows] == expected_queries, photon_rows

# One Overpass operation may use at most two mirrors. Public OSM slowness must
# not cascade through every known mirror and turn one click into minutes.
overpass_calls = []
real_request_json = free._request_json

def failing_request_json(url, **kwargs):
    overpass_calls.append((url, float(kwargs.get("timeout") or 0)))
    raise RuntimeError("simulated slow mirror")

free._request_json = failing_request_json
try:
    try:
        v3._overpass("[out:json];node(0,0,1,1);out;")
    except RuntimeError:
        pass
finally:
    free._request_json = real_request_json
assert 1 <= len(overpass_calls) <= 2, overpass_calls
assert all(timeout <= 3.1 for _, timeout in overpass_calls), overpass_calls

# Campsite lookup used to execute roughly three OSM searches per night. Fast
# mode must fetch one broad pool and filter it locally for nearby stage probes.
lat = 48.60
anchors = [
    {"lat": lat, "lon": -1.50},
    {"lat": lat, "lon": -1.40},
    {"lat": lat, "lon": -1.30},
]
camps = [
    {"name": "Camping A", "lat": lat + 0.008, "lon": -1.50, "category": "camping", "source_url": "a"},
    {"name": "Camping B", "lat": lat + 0.008, "lon": -1.40, "category": "camping", "source_url": "b"},
    {"name": "Camping C", "lat": lat + 0.008, "lon": -1.30, "category": "camping", "source_url": "c"},
]
nearby_calls = {"count": 0}
real_nearby = v3._nearby

def fake_nearby(lat0, lon0, radius, categories):
    nearby_calls["count"] += 1
    return [dict(x) for x in camps] if "camping" in categories else []

v3._nearby = fake_nearby
try:
    speed._STAY_POOLS.clear()
    found = [roundtrip._nearby_stays(v3, anchor, "camping", 4.0) for anchor in anchors]
finally:
    v3._nearby = real_nearby
assert nearby_calls["count"] == 1, nearby_calls
assert all(rows for rows in found), found

# Route-first logistics must reuse the same pooled lookup instead of opening one
# OSM search for every route probe.
route_coords = [
    [lat, -1.54], [lat, -1.48], [lat, -1.42], [lat, -1.36],
    [lat, -1.30], [lat, -1.24],
]
nearby_calls["count"] = 0
v3._nearby = fake_nearby
try:
    speed._STAY_POOLS.clear()
    probe_rows = logistics._route_probe_stays(v3, roundtrip, route_coords, "camping")
finally:
    v3._nearby = real_nearby
assert nearby_calls["count"] <= 1, nearby_calls
assert isinstance(probe_rows, list)

# Walking connectors for several nights must be validated with one ORS Matrix
# batch, not one Directions request per night.
matrix_calls = {"count": 0}
real_matrix = ors.get_distance_matrix

def fake_connector_matrix(points):
    matrix_calls["count"] += 1
    n = len(points)
    matrix = [[0.0 if i == j else 1.2 for j in range(n)] for i in range(n)]
    return {"distances": matrix, "fallback": False, "routing_mode": "ors-matrix"}

ors.get_distance_matrix = fake_connector_matrix
try:
    connector_rows = logistics._matrix_connectors(
        ors,
        route_coords,
        [
            {"name": "A", "lat": lat + 0.005, "lon": -1.48, "_route_index": 1, "_offroute_km": 0.8},
            {"name": "B", "lat": lat + 0.005, "lon": -1.36, "_route_index": 3, "_offroute_km": 0.9},
        ],
    )
finally:
    ors.get_distance_matrix = real_matrix
assert matrix_calls["count"] == 1, matrix_calls
assert len(connector_rows) == 2, connector_rows
assert all(row.get("routing_mode") == "ors-matrix" for row in connector_rows.values())

# ORS Matrix must inherit the short interactive timeout instead of its historical
# 15-second timeout. Use a deterministic fake successful response.
class MatrixResponse:
    status_code = 200
    ok = True
    def json(self):
        return {"distances": [[0.0, 5.0], [5.0, 0.0]]}

post_calls = []
real_post = ors.requests.post
real_key = ors.ORS_API_KEY
ors.ORS_API_KEY = "test-key"

def fake_post(url, **kwargs):
    post_calls.append((url, float(kwargs.get("timeout") or 0)))
    return MatrixResponse()

ors.requests.post = fake_post
try:
    result = ors.get_distance_matrix([[48.60, -1.50], [48.61, -1.40]])
finally:
    ors.requests.post = real_post
    ors.ORS_API_KEY = real_key
assert result.get("fallback") is False, result
assert post_calls and post_calls[0][1] <= 7.1, post_calls

print("TrekBrain v9 interactive latency controls: OK")
