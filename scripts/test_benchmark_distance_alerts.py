"""Offline check: benchmark reports daily overruns that TrekBrain already warns about.

No external calls or database, and no real user plans modified.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_trekbrain_v9_production as bench

CASE = {
    "id": "distance-visibility-test",
    "days": 2, "daily_km": 15,
    "expect_type": "boucle", "expect_close": True,
    "require_water": False, "require_food": False,
    "require_accommodation": False, "require_transit": False,
}

def sample(kms, *, contract=True):
    result = {
        "route_type": "Boucle",
        "start": {"lat": 48.0, "lon": 1.0},
        "end": {"lat": 48.0, "lon": 1.0},
        "route_preview": {
            "coords": [[48.0,1.0],[48.01,1.03],[48.0,1.0]],
            "fallback": False,
            "distance_km": sum(float(x) for x in kms),
            "routing_mode": "pedestrian-validated",
        },
        "stages": [
            {"day":i+1, "distance_km":d, "safety_notes": "Vérifier la distance"}
            for i,d in enumerate(kms)
        ],
        "trekbrain": {"quality": {"score": 87.0}},
    }
    if contract:
        result["planner"] = {"distance_contract": {
            "target_exceeded": True,
            "days_exceeding": [{"day": 1}, {"day": 2}],
        }}
    return result

hike = bench.evaluate(CASE, sample(["18.1",18.1]), 8.0, {})
assert hike["structure_ok"], hike["hard_failures"]
assert not hike["preparation_ok"] and not hike["ok"], hike
assert hike["status"] == "incomplete", hike
assert [x["day"] for x in hike["distance_days_above_target"]] == [1,2], hike
assert hike["distance_days_missing_warning"] == [], hike
assert any("J1 18.1 km (+21%)" in x and "J2 18.1 km (+21%)" in x for x in hike["warnings"]), hike

lost = bench.evaluate(CASE, sample([18.1,18.1],contract=False), 8.0, {})
assert lost["distance_days_missing_warning"] == [1,2], lost
assert any("alerte de distance absente" in x for x in lost["warnings"]), lost

mild = bench.evaluate(CASE, sample([17.1,17.1],contract=False), 8.0, {})
assert mild["distance_days_above_target"] == [], mild
assert not any("distance au-dessus de la demande" in x for x in mild["warnings"]), mild

one = bench.evaluate(CASE, sample([19.0,14.0],contract=False), 8.0, {})
assert [x["day"] for x in one["distance_days_above_target"]] == [1], one
print("Benchmark daily distance: +18%/+2km warning, absent backend notice, modest variation PASS")
