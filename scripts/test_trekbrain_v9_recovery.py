"""Regressions for TrekBrain v9 recovery and failure transparency."""
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from backend import trekbrain_roundtrip_v9 as roundtrip
from backend import trekbrain_failure_diagnostics_v9 as diagnostics


# ---------------------------------------------------------------------------
# 1. A simple loop must still work when the advanced planner cannot build POI
#    candidates. The geometry is mocked as an ORS-validated closed route; the
#    test verifies result compatibility and daily-stage construction.
# ---------------------------------------------------------------------------

fake_coords = [
    [48.600, -1.600],
    [48.600, -1.400],
    [48.760, -1.400],
    [48.760, -1.600],
    [48.600, -1.600],
]

real_roundtrip_request = roundtrip._roundtrip_request
roundtrip._roundtrip_request = lambda start, target_km, seed: ({
    "coords": fake_coords,
    "distance": 80.0,
    "fallback": False,
    "profile": "foot-hiking",
    "routing_mode": "ors-round-trip",
}, None)

class FakeV3:
    @staticmethod
    def _parse_intent(data):
        return {
            "days": 4,
            "daily_target": 20.0,
            "daily_min": 15.0,
            "daily_max": 25.0,
            "total_target": 80.0,
            "route_type": "Boucle",
            "difficulty": "medium",
            "accommodation": "balanced",
            "via_query": "",
            "end_query": "",
        }

    @staticmethod
    def _fold(value):
        return str(value or "").casefold()

    @staticmethod
    def _location(data):
        return data.region

    @staticmethod
    def _geocode(query):
        return [{"name": "Zone test", "lat": 48.600, "lon": -1.600}]

    @staticmethod
    def _route_retrace_ratio(coords):
        return 0.05

    @staticmethod
    def _stage_distances(coords, boundaries, legacy_main, total_distance):
        return [20.0, 20.0, 20.0, 20.0]

    @staticmethod
    def _nearby(lat, lon, radius, categories):
        return []

    @staticmethod
    def _dist(a, b):
        return 1.0


request = SimpleNamespace(
    prompt="Je veux une boucle simple de 4 jours",
    region="Zone test",
    days=4,
    daily_km=20.0,
    difficulty="medium",
    route_type="Boucle",
    require_accommodation=False,
    require_water=False,
    require_transit=False,
)
legacy = SimpleNamespace(
    distance_gps=lambda coords: 80.0,
    elevation_gain=lambda coords: 800,
)

try:
    result = roundtrip._build_roundtrip(request, legacy, FakeV3)
finally:
    roundtrip._roundtrip_request = real_roundtrip_request

assert result["planner_fallback"] == "ors-round-trip", result
assert result["route_preview"]["fallback"] is False, result
assert result["start"]["lat"] == result["end"]["lat"], result
assert result["start"]["lon"] == result["end"]["lon"], result
assert len(result["stages"]) == 4, result
assert [x["distance_km"] for x in result["stages"]] == [20.0, 20.0, 20.0, 20.0], result
print("ORS round-trip recovery: OK")


# ---------------------------------------------------------------------------
# 2. The language layer must not replace a useful ORS/geographic error with the
#    generic 'parcours cohérent' message.
# ---------------------------------------------------------------------------

class FailureV3:
    pass


def geographic_failure(data, legacy_main):
    raise HTTPException(status_code=503, detail="OpenRouteService : quota ou clé indisponible")

FailureV3._build = geographic_failure

class FailureV5:
    pass


def swallowing_v5(data, legacy_main, user_id):
    try:
        FailureV3._build(data, legacy_main)
    except HTTPException:
        pass
    raise HTTPException(
        status_code=422,
        detail="Je n’ai pas trouvé de parcours cohérent avec l’ensemble de ces demandes. Essaie de rendre une contrainte secondaire facultative.",
    )

FailureV5._build = swallowing_v5
FailureV7 = SimpleNamespace(_BASE_BUILD=swallowing_v5)

# Reset only inside this isolated regression process. The production installer
# still executes once per process.
diagnostics._INSTALLED = False
diagnostics.install_failure_diagnostics(FailureV3, FailureV5, FailureV7)

try:
    FailureV7._BASE_BUILD(None, None, 1)
except HTTPException as exc:
    assert exc.status_code == 503, exc
    assert "OpenRouteService" in str(exc.detail), exc
    assert "parcours cohérent" not in str(exc.detail), exc
else:
    raise AssertionError("The real planner failure should have propagated")

print("Underlying planner failure transparency: OK")


# ---------------------------------------------------------------------------
# 3. Reproduce the live v7 topology that caused "maximum recursion depth
#    exceeded": after v7 installation, v5._build points to v7._build while
#    v7._BASE_BUILD still points to the lower-level v5 implementation. The
#    diagnostics installer must NEVER replace v5._build with a wrapper and then
#    point v7._BASE_BUILD at that same wrapper.
# ---------------------------------------------------------------------------

class TopologyV3:
    @staticmethod
    def _build(data, legacy_main):
        return {"low": True}

calls = {"base": 0, "public": 0}

def lower_v5_build(data, legacy_main, user_id):
    calls["base"] += 1
    return {"ok": True, "user_id": user_id}

TopologyV7 = SimpleNamespace(_BASE_BUILD=lower_v5_build)

def public_v7_build(data, legacy_main, user_id):
    calls["public"] += 1
    return TopologyV7._BASE_BUILD(data, legacy_main, user_id)

TopologyV5 = SimpleNamespace(_build=public_v7_build)
original_public = TopologyV5._build

diagnostics._INSTALLED = False
diagnostics.install_failure_diagnostics(TopologyV3, TopologyV5, TopologyV7)

# Critical assertion: diagnostics must leave the public v5 -> v7 edge alone.
assert TopologyV5._build is original_public
result = TopologyV5._build(None, None, 7)
assert result == {"ok": True, "user_id": 7}, result
assert calls == {"base": 1, "public": 1}, calls

print("Production v7 call topology stays acyclic: OK")
