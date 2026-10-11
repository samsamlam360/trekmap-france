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


# Complex request fails twice with HTTP 500, but every two-point ORS leg works.
# The secondary provider must not be called when ORS segmented recovery succeeds.
calls = []
secondary_calls = []

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
real_secondary = resilience._secondary_route
resilience.time.sleep = lambda _seconds: None
resilience._secondary_route = lambda coords: (secondary_calls.append(coords) or None, "should not run")
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
    assert not secondary_calls, secondary_calls
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
    resilience._secondary_route = real_secondary


# Reproduce the production diagnostic TB-ORS-DIR-500: full ORS request + retry
# + first tiny segment all return HTTP 500. TrekBrain must then switch to the
# independent pedestrian router once, rather than returning the ORS failure.
outage_calls = []
secondary_calls = []
def outage_request(coords, _distance_gps, snap_radius_m=None):
    outage_calls.append(len(coords))
    return None, "OpenRouteService indisponible temporairement (HTTP 500).", 500

def secondary_route(coords):
    secondary_calls.append([list(x) for x in coords])
    return {
        "coords": [list(x) for x in coords],
        "distance": 72.4,
        "fallback": False,
        "routing_mode": "valhalla-pedestrian-fallback",
        "provider": "Valhalla/OpenStreetMap",
        "secondary_router": True,
    }, None

ors2 = SimpleNamespace(_request_route=outage_request, ORS_PROFILE="foot-hiking")
resilience._INSTALLED = False
resilience._CACHE.clear()
real_sleep = resilience.time.sleep
real_secondary = resilience._secondary_route
resilience.time.sleep = lambda _seconds: None
resilience._secondary_route = secondary_route
try:
    resilience.install_ors_resilience(ors2)
    coords = [[47.31, -3.23], [47.34, -3.18], [47.32, -3.10], [47.29, -3.14], [47.31, -3.23]]
    route, warning, status = ors2._request_route(coords, distance_gps)
    assert status == 200 and warning is None, (status, warning)
    assert route is not None and route["fallback"] is False
    assert route["routing_mode"] == "valhalla-pedestrian-fallback", route
    assert route["provider"] == "Valhalla/OpenStreetMap"
    assert route["recovered_from_ors_5xx"] is True
    assert len(secondary_calls) == 1, secondary_calls
    # Full request + one retry + first leg + one leg retry, then provider switch.
    assert len(outage_calls) == 4, outage_calls
finally:
    resilience.time.sleep = real_sleep
    resilience._secondary_route = real_secondary

print("ORS HTTP 5xx retry + segmented recovery + secondary pedestrian fallback: OK")


# A legitimate ORS 429 must not be treated as an unsafe straight-line route:
# allow one bounded independent pedestrian fallback and preserve its provenance.
from backend import trekbrain_secondary_router_v9 as secondary

clock = [1000.0]
secondary_calls = []
original_secondary = secondary._route_secondary
original_clock = secondary.time.monotonic
original_installed = secondary._INSTALLED
original_quota = secondary._QUOTA_FALLBACK_NEXT
saved_cache = dict(secondary._CACHE)

def quota_fallback(coords):
    secondary_calls.append(tuple(tuple(p) for p in coords))
    return {
        "coords": [list(p) for p in coords],
        "distance": 12.0,
        "fallback": False,
        "routing_mode": "valhalla-pedestrian-fallback",
        "provider": "Valhalla/OpenStreetMap",
        "secondary_router": True,
    }, None

try:
    secondary.time.monotonic = lambda: clock[0]
    secondary._route_secondary = quota_fallback
    secondary._CACHE.clear()
    secondary._QUOTA_FALLBACK_NEXT = 0
    secondary._INSTALLED = False
    quota_router = SimpleNamespace(get_route=lambda _coords, _distance: {
        "fallback": True, "warning": "OpenRouteService : limite de requêtes atteinte (HTTP 429)."
    })
    secondary.install_secondary_router(quota_router)
    coords = [[42.89, -0.12], [42.91, -0.09]]
    first = quota_router.get_route(coords, distance_gps)
    assert first["fallback"] is False
    assert first["provider"] == "Valhalla/OpenStreetMap"
    assert first["secondary_router"] is True
    assert len(secondary_calls) == 1

    second = quota_router.get_route([[42.87, -0.11], [42.90, -0.07]], distance_gps)
    assert second["fallback"] is True and "temporairement limité" in second["warning"]
    assert len(secondary_calls) == 1, secondary_calls

    # A cached real route can be reused without another public provider call.
    cached_coords = [[42.88, -0.11], [42.91, -0.08]]
    secondary._CACHE[secondary._key(cached_coords)] = (clock[0], dict(first))
    cached = quota_router.get_route(cached_coords, distance_gps)
    assert cached["fallback"] is False and cached["route_cache"] is True
    assert len(secondary_calls) == 1

    clock[0] += 61
    third = quota_router.get_route([[42.86, -0.10], [42.89, -0.07]], distance_gps)
    assert third["fallback"] is False and len(secondary_calls) == 2

    oversized = quota_router.get_route([[42.9, -0.1]] * 9, distance_gps)
    assert oversized["fallback"] is True and len(secondary_calls) == 2

    # Invalid ORS credentials cannot be silently bypassed through Valhalla.
    forbidden_router = SimpleNamespace(get_route=lambda _coords, _distance: {
        "fallback": True, "warning": "OpenRouteService : clé API refusée (HTTP 403)."
    })
    secondary._INSTALLED = False
    secondary.install_secondary_router(forbidden_router)
    forbidden = forbidden_router.get_route(coords, distance_gps)
    assert forbidden["fallback"] is True and len(secondary_calls) == 2
finally:
    secondary._route_secondary = original_secondary
    secondary.time.monotonic = original_clock
    secondary._INSTALLED = original_installed
    secondary._QUOTA_FALLBACK_NEXT = original_quota
    secondary._CACHE.clear()
    secondary._CACHE.update(saved_cache)

print("ORS 429: single budgeted Valhalla fallback, cache, cooldown, oversize and 403: OK")
