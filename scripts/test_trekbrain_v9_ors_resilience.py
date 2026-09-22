"""Regression tests for bounded ORS Directions HTTP 5xx recovery."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_ors_resilience_v9 as resilience


def distance_gps(_coords):
    return 1.0


# Complex request fails twice with HTTP 500, but every two-point leg succeeds.
calls = []

def raw_request(coords, _distance_gps, snap_radius_m=None):
    calls.append((len(coords), snap_radius_m))
    if len(coords) > 2:
        return None, "OpenRouteService indisponible temporairement (HTTP 500).", 500
    a, b = coords
    return {
        "coords": [list(a), list(b)],
        "distance": 5.0,
        "fallback": False,
        "routing_mode": "ors",
        "profile": "foot-hiking",
    }, None, 200

ors = SimpleNamespace(_request_route=raw_request, ORS_PROFILE="foot-hiking")
resilience._INSTALLED = False
resilience._CACHE.clear()
real_sleep = resilience.time.sleep
resilience.time.sleep = lambda _seconds: None
try:
    resilience.install_ors_resilience(ors)
    coords = [[48.60, -1.50], [48.65, -1.42], [48.70, -1.35], [48.75, -1.28]]
    route, warning, status = ors._request_route(coords, distance_gps)
    assert warning is None and status == 200, (warning, status)
    assert route["fallback"] is False
    assert route["routing_mode"] == "ors-segmented-5xx-recovery", route
    assert route["recovered_from_ors_5xx"] is True
    assert route["segments"] == 3
    assert route["distance"] == 15.0
    assert len(route["coords"]) == 4
    # 2 failed full requests + 3 successful legs.
    assert len(calls) == 5, calls

    # Exact repeats are served from the short-lived validated route cache.
    before = len(calls)
    cached, warning, status = ors._request_route(coords, distance_gps)
    assert status == 200 and warning is None
    assert cached.get("route_cache") is True
    assert len(calls) == before, calls
finally:
    resilience.time.sleep = real_sleep


# A real global outage must stop after the first failed segment probe rather
# than exploding into one request per waypoint.
outage_calls = []
def outage_request(coords, _distance_gps, snap_radius_m=None):
    outage_calls.append(len(coords))
    return None, "OpenRouteService indisponible temporairement (HTTP 500).", 500

ors2 = SimpleNamespace(_request_route=outage_request, ORS_PROFILE="foot-hiking")
resilience._INSTALLED = False
resilience._CACHE.clear()
real_sleep = resilience.time.sleep
resilience.time.sleep = lambda _seconds: None
try:
    resilience.install_ors_resilience(ors2)
    coords = [[48.60, -1.50], [48.65, -1.42], [48.70, -1.35], [48.75, -1.28], [48.80, -1.20]]
    route, warning, status = ors2._request_route(coords, distance_gps)
    assert route is None and status == 500
    assert "segment pédestre 1/4" in warning
    # Full request + one retry + first leg + one leg retry, then stop.
    assert len(outage_calls) == 4, outage_calls
finally:
    resilience.time.sleep = real_sleep

print("ORS HTTP 5xx retry + bounded segmented recovery: OK")
