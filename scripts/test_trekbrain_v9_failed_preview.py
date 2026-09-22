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
assert captured["provisional"] is True
assert captured["warning"] == "ORS 500"

# Clearing the request context must make stale geometry unavailable.
preview.clear_failed_preview()
assert preview.get_failed_preview() is None

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
assert captured["provisional"] is True

assert overlay._error_message("Erreur simple") == "Erreur simple"
assert overlay._error_message({"message": "Erreur structurée"}) == "Erreur structurée"

print("Failed-plan provisional preview capture: OK")
