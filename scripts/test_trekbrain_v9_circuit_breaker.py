"""Regression tests for TrekBrain v9 network timeout circuit breakers."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_circuit_breaker_v9 as cb
from backend import free_planner_v2 as free

calls = {"overpass": 0, "route": 0, "matrix": 0, "roundtrip": 0}


def slow_overpass(query):
    calls["overpass"] += 1
    raise RuntimeError("Overpass délai dépassé")


def slow_route(coords, distance_gps, snap_radius_m=None):
    calls["route"] += 1
    return None, "OpenRouteService : délai interactif dépassé.", None


def slow_matrix(coords):
    calls["matrix"] += 1
    return {"distances": None, "fallback": True, "warning": "OpenRouteService Matrix : délai interactif dépassé."}


def slow_roundtrip(start, target_km, seed):
    calls["roundtrip"] += 1
    return None, "OpenRouteService round-trip : délai interactif dépassé."

v3 = SimpleNamespace(_overpass=slow_overpass)
ors = SimpleNamespace(_request_route=slow_route, get_distance_matrix=slow_matrix)
roundtrip = SimpleNamespace(_roundtrip_request=slow_roundtrip)

real_free_overpass = free._overpass
try:
    cb._INSTALLED = False
    cb._STATE.update({"overpass": 0.0, "ors": 0.0, "matrix": 0.0})
    cb.install_circuit_breakers(v3, ors, roundtrip)

    for _ in range(2):
        try:
            v3._overpass("query")
        except RuntimeError:
            pass
    assert calls["overpass"] == 1, calls

    first = ors._request_route([[0, 0], [1, 1]], lambda x: 1)
    second = ors._request_route([[0, 0], [1, 1]], lambda x: 1)
    assert first[2] == 599 and second[2] == 599, (first, second)
    assert calls["route"] == 1, calls

    one = ors.get_distance_matrix([[0, 0], [1, 1]])
    two = ors.get_distance_matrix([[0, 0], [1, 1]])
    assert one.get("fallback") and two.get("fallback"), (one, two)
    assert calls["matrix"] == 1, calls

    # ORS directions circuit is already open, so fallback round-trip must not
    # spend another network timeout immediately afterwards.
    route, warning = roundtrip._roundtrip_request({"lat": 0, "lon": 0}, 20, 3)
    assert route is None and "timeout" in warning.casefold(), warning
    assert calls["roundtrip"] == 0, calls
finally:
    free._overpass = real_free_overpass

print("TrekBrain v9 timeout circuit breakers: OK")

# A provider 429 must stop alternative Directions calls, survive the next
# user request's timeout reset, expire, and leave Matrix independent.
clock = [100.0]
original_clock = cb.time.monotonic
quota_calls = {"route": 0, "matrix": 0}
def limited_route(*args):
    quota_calls["route"] += 1
    return None, "OpenRouteService HTTP 429", 429
def healthy_matrix(*args):
    quota_calls["matrix"] += 1
    return {"distances": [[0, 1], [1, 0]], "fallback": False}
try:
    cb.time.monotonic = lambda: clock[0]
    cb.reset_circuit_breakers()
    cb._RATE_LIMITED_UNTIL.update(ors=0, matrix=0)
    cb._INSTALLED = False
    quota_ors = SimpleNamespace(_request_route=limited_route, get_distance_matrix=healthy_matrix)
    quota_roundtrip = SimpleNamespace(_roundtrip_request=slow_roundtrip)
    cb.install_circuit_breakers(SimpleNamespace(_overpass=slow_overpass), quota_ors, quota_roundtrip)
    assert quota_ors._request_route([], None)[2] == 429
    cb.reset_circuit_breakers()
    assert quota_ors._request_route([], None)[2] == 429
    assert "429" in quota_roundtrip._roundtrip_request({}, 20, 1)[1]
    assert quota_calls["route"] == 1
    assert not quota_ors.get_distance_matrix([])["fallback"]
    clock[0] = 161
    quota_ors._request_route([], None)
    assert quota_calls["route"] == 2
    cb._report_rate_limit("matrix", "OpenRouteService Matrix HTTP 429")
    assert quota_ors.get_distance_matrix([])["fallback"]
    assert quota_calls["matrix"] == 1
finally:
    cb.time.monotonic = original_clock
    cb._RATE_LIMITED_UNTIL.update(ors=0, matrix=0)
    cb.reset_circuit_breakers()
    free._overpass = real_free_overpass
print("ORS 429: shared Directions cooldown, reset resistance, expiry and Matrix isolation: OK")
