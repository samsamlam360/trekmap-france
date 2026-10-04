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
from backend import trekbrain_ors_resilience_v9 as resilience

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

# Explicit refuge/camping logistics already constrains the useful candidate
# family strongly. Keep one candidate per strategy even for an itinerary,
# while the outer planner still compares its three strategies.
refuge_rows = speed._prune_route_candidates(
    traverse_rows,
    {
        "route_type": "Itinérance",
        "start_query": "",
        "end_query": "",
        "accommodation": "refuge",
    },
)
assert len(refuge_rows) == 1, [x.strategy for x in refuge_rows]

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

# A first ORS loop already within 20% of the requested total and with a
# reasonable retrace is good enough for interactive planning. Returning it
# immediately removes a second provider round trip for Sancy/Morvan-like cases.
real_good_request = roundtrip._roundtrip_request
real_good_retrace = v3._route_retrace_ratio
good_calls = []

def fake_good_roundtrip(start, requested_km, seed):
    good_calls.append((float(requested_km), int(seed)))
    return {
        "coords": [[45.53, 2.82], [45.60, 2.90], [45.48, 2.95], [45.53, 2.82]],
        "distance": 59.5,
        "fallback": False,
        "routing_mode": "ors-round-trip",
    }, None

roundtrip._roundtrip_request = fake_good_roundtrip
v3._route_retrace_ratio = lambda coords: 0.22
try:
    good_loop = roundtrip._best_roundtrip(
        {"lat": 45.53, "lon": 2.82},
        51.0,
        12.75,
        21.25,
        3,
        v3,
    )
finally:
    roundtrip._roundtrip_request = real_good_request
    v3._route_retrace_ratio = real_good_retrace

assert len(good_calls) == 1, good_calls
assert good_loop.get("single_call_good_enough") is True, good_loop
assert good_loop.get("round_trip_attempt_count") == 1, good_loop
assert len(good_loop.get("round_trip_attempts") or []) == 1, good_loop
assert good_loop.get("candidate_pool_size") == 1, good_loop

# A route that is technically inside the broad +/-25% feasibility window but
# still far from the requested target must receive the corrective second ORS
# call. This protects Vercors quality: ~18.7 km/day is feasible for a 15 km
# target, but a second calibrated request can produce ~15.1 km/day.
real_roundtrip_request = roundtrip._roundtrip_request
roundtrip_calls = []
def fake_soft_roundtrip(start, requested_km, seed):
    roundtrip_calls.append((float(requested_km), int(seed)))
    distance = 56.2 if len(roundtrip_calls) == 1 else 45.3
    return {
        "coords": [[45.0, 5.0], [45.08, 5.08], [44.98, 5.15], [45.0, 5.0]],
        "distance": distance,
        "fallback": False,
        "routing_mode": "ors-round-trip",
    }, None

roundtrip._roundtrip_request = fake_soft_roundtrip
try:
    corrected_loop = roundtrip._best_roundtrip(
        {"lat": 45.0, "lon": 5.0},
        45.0,
        11.25,
        18.75,
        3,
        v3,
    )
finally:
    roundtrip._roundtrip_request = real_roundtrip_request
assert len(roundtrip_calls) == 2, roundtrip_calls
assert roundtrip_calls[1][0] < roundtrip_calls[0][0], roundtrip_calls
assert float(corrected_loop.get("distance") or 0) == 45.3, corrected_loop

# When two ORS variants are already available, a materially more precise
# distance must beat a much longer loop even when the precise option retraces a
# little more. No third network call is allowed.
real_precision_request = roundtrip._roundtrip_request
real_retrace = v3._route_retrace_ratio
precision_calls = []
def fake_precision_roundtrip(start, requested_km, seed):
    precision_calls.append((float(requested_km), int(seed)))
    if len(precision_calls) == 1:
        return {
            "coords": [[48.636, -1.511], [48.700, -1.430], [48.600, -1.350], [48.636, -1.511]],
            "distance": 40.86,
            "fallback": False,
            "routing_mode": "ors-round-trip",
        }, None
    return {
        "coords": [[48.637, -1.511], [48.690, -1.455], [48.610, -1.390], [48.637, -1.511]],
        "distance": 34.0,
        "fallback": False,
        "routing_mode": "ors-round-trip",
    }, None

def fake_retrace(coords):
    return 0.02 if coords and abs(float(coords[0][0]) - 48.636) < 1e-6 else 0.22

roundtrip._roundtrip_request = fake_precision_roundtrip
v3._route_retrace_ratio = fake_retrace
try:
    precise_loop = roundtrip._best_roundtrip(
        {"lat": 48.636, "lon": -1.511},
        32.0,
        12.0,
        20.0,
        2,
        v3,
    )
finally:
    roundtrip._roundtrip_request = real_precision_request
    v3._route_retrace_ratio = real_retrace

assert len(precision_calls) == 2, precision_calls
assert float(precise_loop.get("distance") or 0) == 34.0, precise_loop
assert float(precise_loop.get("round_trip_retrace_ratio") or 0) <= 0.30, precise_loop

# Route-first lodging must not start a third route-probe network path after
# Photon and the single bounded bbox lookup fail.
real_photon_split = logistics._photon_split_stays
real_bbox_stays = logistics._bbox_route_stays
real_route_probe = logistics._route_probe_stays
logistics._photon_split_stays = lambda *args, **kwargs: []
logistics._bbox_route_stays = lambda *args, **kwargs: []
def forbidden_route_probe(*args, **kwargs):
    raise AssertionError("route probe must not be called from _discover_stays")
logistics._route_probe_stays = forbidden_route_probe
try:
    chosen, projected, meta = logistics._discover_stays(
        v3,
        roundtrip,
        object(),
        route_coords,
        {"lat": lat, "lon": -1.54},
        "camping",
        3,
        18.0,
        False,
    )
finally:
    logistics._photon_split_stays = real_photon_split
    logistics._bbox_route_stays = real_bbox_stays
    logistics._route_probe_stays = real_route_probe
assert chosen == [] and projected == [], (chosen, projected)
assert float(meta.get("elapsed_ms") or 0) < 500, meta

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

# A network timeout must not trigger the old snapped/segmented ORS retry chain.
# The resilience layer marks it as a transient provider failure (599), allowing
# the already-installed secondary router to take over after one primary attempt.
class TimeoutORS:
    ORS_PROFILE = "foot-hiking"
    def __init__(self):
        self.calls = 0
        self._request_route = self.raw_request
    def raw_request(self, coords, distance_gps, snap_radius_m=None):
        self.calls += 1
        return None, "OpenRouteService : délai d'attente dépassé.", None

timeout_ors = TimeoutORS()
real_resilience_installed = resilience._INSTALLED
try:
    resilience._INSTALLED = False
    resilience.install_ors_resilience(timeout_ors)
    timeout_result, timeout_warning, timeout_status = timeout_ors._request_route(
        [[48.0, 2.0], [48.1, 2.1]],
        lambda _coords: 10.0,
    )
finally:
    resilience._INSTALLED = real_resilience_installed

assert timeout_result is None, timeout_result
assert timeout_ors.calls == 1, timeout_ors.calls
assert timeout_status == 599, (timeout_warning, timeout_status)
assert resilience._is_transport_failure(timeout_warning, None) is True

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

# A short soft-tolerance loop may legitimately end a few hundred metres
# above daily_max after two ranked ORS variants. Once those variants have
# already been compared, the raw-route recovery must not launch another ORS
# calibration pass just because its older threshold is slightly stricter.
real_roundtrip_request_ranked = roundtrip._roundtrip_request
ranked_calls = []

def fake_ranked_roundtrip(start, requested_km, seed):
    ranked_calls.append((round(float(requested_km), 2), int(seed)))
    return {
        "coords": [
            [48.636, -1.511],
            [48.700, -1.430],
            [48.600, -1.350],
            [48.636, -1.511],
        ],
        "distance": 40.86,
        "fallback": False,
        "routing_mode": "ors-round-trip",
    }, None

roundtrip._roundtrip_request = fake_ranked_roundtrip
try:
    ranked = roundtrip._best_roundtrip(
        {"lat": 48.636, "lon": -1.511},
        32.0,
        12.0,
        20.0,
        2,
        v3,
    )
finally:
    roundtrip._roundtrip_request = real_roundtrip_request_ranked

assert len(ranked_calls) == 2, ranked_calls
assert ranked.get("fast_ranked") is True, ranked
assert ranked.get("candidate_pool_size") == 2, ranked

recovery_calls = []
real_recovery_request = roundtrip._roundtrip_request
roundtrip._roundtrip_request = lambda *args, **kwargs: recovery_calls.append(args) or (None, "should not run")
try:
    recovered_ranked = roundtrip._recover_unranked_oversized_roundtrip(
        ranked,
        {"lat": 48.636, "lon": -1.511},
        32.0,
        12.0,
        20.0,
        2,
        v3,
    )
finally:
    roundtrip._roundtrip_request = real_recovery_request

assert recovered_ranked is ranked, (recovered_ranked, ranked)
assert recovery_calls == [], recovery_calls

print("TrekBrain v9 interactive latency controls: OK")
