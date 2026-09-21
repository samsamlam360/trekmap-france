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
