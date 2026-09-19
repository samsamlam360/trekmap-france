"""Offline safety regressions for TrekBrain v9.2.

These tests exist because a hiking adviser must never turn a routing failure
into a convincing straight line across the sea.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.trekbrain_geo_safety_v9 import (
    _inside_bounds,
    _is_island_hint,
    route_safety_report,
)


request = SimpleNamespace(
    prompt="Je veux faire le tour de Belle-Île en 5 jours et dormir dans des campings",
    days=5,
    require_water=True,
)

# A compact but continuous routed loop. Precision/target-distance checks belong
# to the planner audit; this test focuses on the hard geographic safety gate.
good = {
    "route_preview": {
        "fallback": False,
        "coords": [
            [47.3300, -3.1800],
            [47.3310, -3.1700],
            [47.3370, -3.1660],
            [47.3400, -3.1750],
            [47.3340, -3.1840],
            [47.3300, -3.1800],
        ],
    },
    "start": {"lat": 47.3300, "lon": -3.1800},
    "end": {"lat": 47.3300, "lon": -3.1800},
    "stages": [
        {"distance_km": 2.0, "overnight": "Camping 1", "water_notes": "Fontaine à vérifier"},
        {"distance_km": 2.0, "overnight": "Camping 2", "water_notes": "Point d'eau à vérifier"},
        {"distance_km": 2.0, "overnight": "Camping 3", "water_notes": "Fontaine à vérifier"},
        {"distance_km": 2.0, "overnight": "Camping 4", "water_notes": "Point d'eau à vérifier"},
        {"distance_km": 2.0, "overnight": "Arrivée", "water_notes": "Fontaine à vérifier"},
    ],
    "accommodations": [
        {"name": "Camping 1", "category": "camping"},
        {"name": "Camping 2", "category": "camping"},
        {"name": "Camping 3", "category": "camping"},
        {"name": "Camping 4", "category": "camping"},
    ],
}

report = route_safety_report(good, request)
assert report["safe"], report
assert report["routing_verified"] is True, report

# The bug from the real Belle-Île report: router failure followed by a straight
# line. This must be a hard rejection, never a low-confidence recommendation.
fallback = deepcopy(good)
fallback["route_preview"] = {
    "fallback": True,
    "coords": [[47.33, -3.18], [47.47, -3.12], [47.56, -3.06]],
}
fallback_report = route_safety_report(fallback, request)
assert not fallback_report["safe"], fallback_report
assert any("moteur pédestre" in item for item in fallback_report["blockers"]), fallback_report

# Even a response accidentally labelled as routed is rejected if its geometry
# contains a huge geographic teleport between consecutive points.
sea_jump = deepcopy(good)
sea_jump["route_preview"] = {
    "fallback": False,
    "coords": [[47.33, -3.18], [47.47, -3.12], [47.56, -3.06]],
}
sea_report = route_safety_report(sea_jump, request)
assert not sea_report["safe"], sea_report
assert sea_report["max_segment_gap_km"] > 3, sea_report

# If the user explicitly asks for camping every night, invented generic
# overnight labels are not sufficient.
missing_camp = deepcopy(good)
missing_camp["stages"][2]["overnight"] = "Nuitée à confirmer"
camp_report = route_safety_report(missing_camp, request)
assert not camp_report["safe"], camp_report
assert any("camping" in item.casefold() for item in camp_report["blockers"]), camp_report

# Island filtering must keep Belle-Île points while excluding mainland points.
assert _is_island_hint("Belle-Île-en-Mer")
assert _is_island_hint("île de Groix")
assert not _is_island_hint("Vercors")

bounds = {"south": 47.25, "north": 47.40, "west": -3.30, "east": -3.05}
assert _inside_bounds({"lat": 47.33, "lon": -3.18}, bounds)
assert not _inside_bounds({"lat": 47.60, "lon": -3.00}, bounds)

print("TrekBrain v9.2 geographic safety tests: OK")
