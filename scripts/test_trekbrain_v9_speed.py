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
from backend import trekbrain_speed_v9 as speed

# This test validates the default interactive profile, not an operator override.
os.environ.pop("TREKBRAIN_RETRY_BUDGET_SECONDS", None)
os.environ.pop("TREKBRAIN_OVERPASS_BUDGET_SECONDS", None)
os.environ.pop("TREKBRAIN_ORS_TIMEOUT_SECONDS", None)
os.environ.pop("TREKBRAIN_MATRIX_TIMEOUT_SECONDS", None)

speed._INSTALLED = False
speed._STAY_POOLS.clear()
speed.install_fast_planning(v3, v5, v9)

# A second complete geographic hypothesis is not part of the default interactive
# path. The lower layers already compare route candidates.
assert v9.seconds("TREKBRAIN_RETRY_BUDGET_SECONDS", 10) == 0.0

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
