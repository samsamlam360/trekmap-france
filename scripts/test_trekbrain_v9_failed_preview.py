"""Regression tests for request-local provisional route capture."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_failed_preview_v9 as preview
from backend import trekbrain_request_overlay_v9 as overlay


calls = []

def fake_get_route(coords, distance_gps):
    calls.append(coords)
    return {
        "coords": [list(x) for x in coords],
        "distance": 23.456,
        "fallback": True,
        "routing_mode": "unvalidated-direct-diagnostic",
        "warning": "ORS 500",
    }

ors = SimpleNamespace(get_route=fake_get_route)
preview._INSTALLED = False
preview.clear_failed_preview()
preview.install_failed_preview_capture(ors)

coords = [[48.63, -1.51], [48.67, -1.44], [48.71, -1.38]]
result = ors.get_route(coords, lambda _x: 20)
assert result["fallback"] is True
captured = preview.get_failed_preview()
assert captured is not None
assert captured["coords"] == coords
assert captured["distance_km"] == 23.46
assert captured["routing_validated"] is False
assert captured["candidate_only"] is False
assert captured["provisional"] is True
assert captured["warning"] == "ORS 500"

# Clearing the request context must make stale geometry unavailable.
preview.clear_failed_preview()
assert preview.get_failed_preview() is None

# Crucial production regression: even if the wrapped routing layer raises before
# returning a result, the candidate waypoints must already be available to the
# "Voir quand même" action.
def raising_get_route(coords, distance_gps):
    raise RuntimeError("simulated ORS worker failure")

ors_raising = SimpleNamespace(get_route=raising_get_route)
preview._INSTALLED = False
preview.install_failed_preview_capture(ors_raising)
preview.clear_failed_preview()
try:
    ors_raising.get_route(coords, lambda _x: 21.7)
except RuntimeError:
    pass
else:
    raise AssertionError("The simulated routing failure should propagate")
captured = preview.get_failed_preview()
assert captured is not None
assert captured["coords"] == coords
assert captured["candidate_only"] is True
assert captured["routing_validated"] is False
assert captured["distance_km"] == 21.7

# A validated ORS route can also be inspected if a later planner constraint
# rejects the full plan. It remains labelled provisional at the UI level.
def validated_get_route(coords, distance_gps):
    return {
        "coords": [list(x) for x in coords],
        "distance": 19.0,
        "fallback": False,
        "routing_mode": "ors",
    }

ors2 = SimpleNamespace(get_route=validated_get_route)
preview._INSTALLED = False
preview.install_failed_preview_capture(ors2)
ors2.get_route(coords[:2], lambda _x: 19)
captured = preview.get_failed_preview()
assert captured["routing_validated"] is True
assert captured["candidate_only"] is False
assert captured["provisional"] is True

# The round-trip fallback bypasses ors.get_route in production. Its real ORS
# geometry therefore needs an explicit capture hook, otherwise a route rejected
# later for daily mileage leaves the UI button with no geometry.
def inert_get_route(coords, distance_gps):
    return {"coords": coords, "distance": 1.0, "fallback": True}

def fake_roundtrip(start, target_km, seed):
    return ({
        "coords": [[48.60, -1.50], [48.70, -1.45], [48.60, -1.50]],
        "distance": 30.7,
        "fallback": False,
        "routing_mode": "ors-round-trip",
    }, None)

ors3 = SimpleNamespace(get_route=inert_get_route)
roundtrip = SimpleNamespace(_roundtrip_request=fake_roundtrip)
preview._INSTALLED = False
preview.clear_failed_preview()
preview.install_failed_preview_capture(ors3, roundtrip)
route, warning = roundtrip._roundtrip_request({"lat": 48.6, "lon": -1.5}, 30.0, 11)
assert warning is None
assert route["distance"] == 30.7
captured = preview.get_failed_preview()
assert captured is not None
assert captured["routing_mode"] == "ors-round-trip"
assert captured["routing_validated"] is True
assert captured["candidate_only"] is False
assert len(captured["coords"]) == 3

assert overlay._error_message("Erreur simple") == "Erreur simple"
assert overlay._error_message({"message": "Erreur structurée"}) == "Erreur structurée"

print("Failed-plan provisional preview capture: OK")
