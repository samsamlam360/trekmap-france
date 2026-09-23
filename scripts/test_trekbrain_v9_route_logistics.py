"""Regression: lodging must not reshape the hiking route, with or without a GR."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_route_logistics_v9 as logistics
from backend import trekbrain_route_logistics_guard_v9 as logistics_guard


class Data:
    prompt = "Je veux une boucle de 5 jours à 20 km par jour avec des campings tous les soirs"
    region = "Zone test"
    days = 5
    daily_km = 20
    require_accommodation = True

    def model_copy(self, update=None):
        clone = Data()
        for key, value in (update or {}).items():
            setattr(clone, key, value)
        return clone


class FakeRoundtrip:
    @staticmethod
    def _haversine(a, b):
        # Synthetic route uses 0.01° longitude ~= 1 km for this test.
        return abs(float(b[1]) - float(a[1])) * 100.0

    @staticmethod
    def _cumulative(coords):
        out = [0.0]
        for a, b in zip(coords, coords[1:]):
            out.append(out[-1] + FakeRoundtrip._haversine(a, b))
        return out

    @staticmethod
    def _route_index_for_progress(cum, progress):
        return min(range(len(cum)), key=lambda i: abs(cum[i] - progress))

    @staticmethod
    def _project_stay_to_route(coords, cum, stay):
        index = int(round(float(stay["lon"]) * 100))
        index = max(0, min(index, len(coords) - 1))
        off = abs(float(stay["lat"])) * 100.0
        return index, float(cum[index]), off


class FakeV3:
    def __init__(self):
        self._build_calls = []

    @staticmethod
    def _parse_intent(data):
        text = str(data.prompt).casefold()
        return {
            "days": 5,
            "daily_target": 20.0,
            "daily_min": 15.0,
            "daily_max": 25.0,
            "route_type": "Boucle",
            "accommodation": "camping" if "camping" in text else "balanced",
        }

    @staticmethod
    def _nearby(*args, **kwargs):
        return []


class FakeStayRescue:
    @staticmethod
    def _photon_stays(*args, **kwargs):
        return []

    @staticmethod
    def _nominatim_stays(*args, **kwargs):
        return []


class FakeORS:
    @staticmethod
    def get_route(coords, distance_func):
        # Every short connector is validated. Its distance is roughly the
        # vertical synthetic offset in this test.
        distance = abs(float(coords[-1][0]) - float(coords[0][0])) * 100.0
        return {"coords": coords, "distance": max(0.2, distance), "fallback": False, "routing_mode": "fake-walk"}


class FakeLegacy:
    @staticmethod
    def distance_gps(coords):
        return 100.0 if len(coords) > 10 else 1.0


coords = [[0.0, i / 100.0] for i in range(101)]
base_result = {
    "title": "Boucle sans GR",
    "route_type": "Boucle",
    "duration_days": 5,
    "start": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "end": {"name": "Départ", "lat": 0.0, "lon": 0.0},
    "route_preview": {"coords": coords, "distance_km": 100.0, "distance": 100.0, "fallback": False, "routing_mode": "ors"},
    "stages": [{"day": i + 1, "distance_km": 20.0, "overnight": "Étape"} for i in range(5)],
    "advisor_notes": [],
    "planner": {},
}

# Campsites lie near ideal 20/40/60/80 km splits. The third one is deliberately
# farther from the route and should become transfer logistics instead of making
# a 30 km hiking day.
camps = [
    {"name": "Camping A", "lat": 0.010, "lon": 0.20, "category": "camping", "source_url": "osm://a"},
    {"name": "Camping B", "lat": 0.015, "lon": 0.40, "category": "camping", "source_url": "osm://b"},
    {"name": "Camping C", "lat": 0.045, "lon": 0.60, "category": "camping", "source_url": "osm://c"},
    {"name": "Camping D", "lat": 0.012, "lon": 0.80, "category": "camping", "source_url": "osm://d"},
]

real_bbox = logistics._bbox_route_stays
logistics._bbox_route_stays = lambda _coords, category: [dict(x) for x in camps]
try:
    v3 = FakeV3()

    def original_build(data, legacy):
        v3._build_calls.append((data.prompt, getattr(data, "require_accommodation", None)))
        return {**base_result, "route_preview": dict(base_result["route_preview"]), "stages": [dict(x) for x in base_result["stages"]], "advisor_notes": [], "planner": {}}

    v3._build = original_build
    logistics._INSTALLED = False
    logistics.install_route_first_logistics(v3, FakeRoundtrip, FakeStayRescue, FakeORS)
    result = v3._build(Data(), FakeLegacy())
finally:
    logistics._bbox_route_stays = real_bbox

# Main route is built with lodging removed, proving camping does not shape geometry.
assert len(v3._build_calls) == 1, v3._build_calls
assert "camping" not in v3._build_calls[0][0].casefold(), v3._build_calls
assert v3._build_calls[0][1] is False
assert result["route_preview"]["coords"] == coords
assert result["route_preview"]["distance_km"] == 100.0
assert result["planner"]["logistics_mode"] == "route-first"
assert result["logistics"]["nights_required"] == 4
assert result["logistics"]["nights_resolved"] == 4
assert len(result["accommodations"]) == 4
assert all(float(stage["distance_km"]) == 20.0 for stage in result["stages"])
assert max(float(stage["distance_km"]) for stage in result["stages"]) <= 25.0

# The distant campsite remains useful but does not deform the hiking route.
night3 = result["logistics"]["nights"][2]
assert night3["name"] == "Camping C"
assert night3["access_mode"] == "transfer", night3
assert "transfert" in result["stages"][2]["overnight"].casefold()

# Production guard: even if lodging post-processing throws an unexpected Python
# exception, a valid pedestrian route must still be returned instead of
# TB-INTERNAL-500.
v3_guard = FakeV3()

def base_build_guard(data, legacy):
    return {**base_result, "route_preview": dict(base_result["route_preview"]), "stages": [dict(x) for x in base_result["stages"]], "advisor_notes": [], "planner": {}}

v3_guard._build = base_build_guard
logistics._INSTALLED = False
logistics_guard._INSTALLED = False
logistics.install_route_first_logistics(v3_guard, FakeRoundtrip, FakeStayRescue, FakeORS)
wrapped_route_first = v3_guard._build

# Force the exact post-route failure class seen in production: the route exists,
# then lodging enrichment crashes for an unrelated reason.
real_attach = logistics._attach_logistics
try:
    def boom(*args, **kwargs):
        raise RuntimeError("synthetic lodging crash")
    logistics._attach_logistics = boom
    logistics_guard.install_route_logistics_guard(v3_guard)
    degraded = v3_guard._build(Data(), FakeLegacy())
finally:
    logistics._attach_logistics = real_attach

assert degraded["route_preview"]["coords"] == coords
assert degraded["route_preview"]["fallback"] is False
assert degraded["logistics"]["status"] == "degraded"
assert degraded["logistics"]["error_code"] == "TB-LOGISTICS-DEGRADED"
assert degraded["planner"]["lodging_does_not_shape_route"] is True

print("Route-first lodging logistics + fail-open recovery: OK")
