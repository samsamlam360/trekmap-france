"""TrekBrain v9 release gate: five reference scenarios must survive together.

The fully wired app is imported once so this catches wrapper-order regressions,
then the five product reference cases are checked without live network calls.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("TREKBRAIN_VERSION", "v9")
os.environ.setdefault("TREKBRAIN_FREE_MODE", "1")
os.environ.setdefault("ORS_API_KEY", "ci-placeholder")

from backend import app_v5  # noqa: E402
from backend import smart_planner_v7 as v7  # noqa: E402
from backend import trekbrain_request_v9 as request_v9  # noqa: E402
from backend.free_planner_v2 import AIPlanRequest  # noqa: E402
from backend.trekbrain_stability_contract_v9 import assert_reference  # noqa: E402

assert app_v5.TREKBRAIN_VERSION == "v9"


def wrapped_chain(fn):
    rows, seen, current = [], set(), fn
    for _ in range(40):
        if not callable(current) or id(current) in seen:
            break
        seen.add(id(current))
        rows.append(f"{getattr(current, '__module__', '?')}.{getattr(current, '__name__', '?')}")
        closure = getattr(current, "__closure__", None) or ()
        names = getattr(getattr(current, "__code__", None), "co_freevars", ())
        values = {}
        for name, cell in zip(names, closure):
            try:
                values[name] = cell.cell_contents
            except ValueError:
                pass
        next_fn = None
        for key in ("current_v3_build", "original_build", "previous_build", "base_build", "wrapped_build", "inner_build"):
            value = values.get(key)
            if inspect.isfunction(value) and id(value) not in seen:
                next_fn = value
                break
        if next_fn is None:
            break
        current = next_fn
    return rows


chain = wrapped_chain(v7.v5.v3._build)
critical = [
    "backend.trekbrain_failure_diagnostics_v9",
    "backend.trekbrain_route_logistics_guard_v9",
    "backend.trekbrain_route_logistics_v9",
    "backend.trekbrain_belle_ile_canonical_v9",
]
positions = {}
for module in critical:
    matches = [i for i, row in enumerate(chain) if row.startswith(module + ".")]
    assert matches, f"Missing critical wrapper {module}. Chain: {chain}"
    positions[module] = matches[0]
assert [positions[x] for x in critical] == sorted(positions[x] for x in critical), chain


real_geocode = request_v9.geo._geocode


def fake_geocode(query):
    text = request_v9._fold(query).replace("-", " ").replace("’", " ").replace("'", " ")
    rows = [
        (("belle ile",), {"name": "Belle-Île-en-Mer", "short_name": "Belle-Île-en-Mer", "lat": 47.3331, "lon": -3.1870}),
        (("mont saint michel", "mont st michel"), {"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.6361, "lon": -1.5115}),
        (("chartres",), {"name": "Chartres", "short_name": "Chartres", "lat": 48.4469, "lon": 1.4890}),
        (("tours",), {"name": "Tours", "short_name": "Tours", "lat": 47.3941, "lon": 0.6848}),
        (("chinon",), {"name": "Chinon", "short_name": "Chinon", "lat": 47.1670, "lon": 0.2428}),
        (("bretagne",), {"name": "Bretagne", "short_name": "Bretagne", "lat": 48.20, "lon": -2.93}),
    ]
    for needles, row in rows:
        if any(needle in text for needle in needles):
            return [dict(row)]
    return []


request_v9.geo._geocode = fake_geocode
try:
    belle = AIPlanRequest(
        prompt="Je veux faire le tour de Belle-Île en 5 jours, environ 18 km par jour",
        region="Bretagne", days=5, daily_km=18, route_type="Traversée",
        require_accommodation=False,
    )
    resolved, meta = request_v9.reconcile_request(belle)
    assert resolved.region == "Belle-Île-en-Mer", (resolved.region, meta)
    assert resolved.route_type == "Boucle"
    assert "gr 340" in request_v9._fold(resolved.prompt)
    assert meta["island_access_mode"] == "transport-then-hike"

    belle_camp = AIPlanRequest(
        prompt="Je veux faire le tour de Belle-Île en 5 jours à environ 18 km par jour avec des campings tous les soirs",
        region="Bretagne", days=5, daily_km=18, route_type="Traversée",
        require_accommodation=True,
    )
    resolved, _ = request_v9.reconcile_request(belle_camp)
    intent = v7.v5.v3._parse_intent(resolved)
    assert resolved.route_type == "Boucle"
    assert intent["accommodation"] == "camping"
    assert int(intent["days"]) == 5

    mont = AIPlanRequest(
        prompt="Je veux faire un trek de 4 jours autour du Mont St Michel, en boucle, environ 20 km par jour",
        region="Belle-Île-en-Mer", days=5, daily_km=18, route_type="Traversée",
        require_accommodation=False,
    )
    resolved, meta = request_v9.reconcile_request(mont)
    intent = v7.v5.v3._parse_intent(resolved)
    assert resolved.region == "Mont Saint-Michel", (resolved.region, meta)
    assert resolved.route_type == "Boucle"
    assert int(intent["days"]) == 4
    assert abs(float(intent["daily_target"]) - 20.0) < 0.1

    loop = AIPlanRequest(
        prompt="Je veux une boucle de 4 jours autour de Chartres à environ 20 km par jour",
        region="Chartres", days=4, daily_km=20, route_type="Boucle",
        require_accommodation=False,
    )
    resolved, _ = request_v9.reconcile_request(loop)
    intent = v7.v5.v3._parse_intent(resolved)
    assert resolved.route_type == "Boucle"
    assert int(intent["days"]) == 4 and abs(float(intent["daily_target"]) - 20.0) < 0.1

    traverse = AIPlanRequest(
        prompt="Je veux une traversée de 3 jours entre Tours et Chinon à environ 18 km par jour",
        region="Tours", days=3, daily_km=18, route_type="Traversée",
        require_accommodation=False,
    )
    resolved, _ = request_v9.reconcile_request(traverse)
    intent = v7.v5.v3._parse_intent(resolved)
    assert resolved.route_type == "Traversée"
    assert int(intent["days"]) == 3 and abs(float(intent["daily_target"]) - 18.0) < 0.1
finally:
    request_v9.geo._geocode = real_geocode


def stages(values):
    return [{"day": i + 1, "distance_km": float(d), "overnight": "Étape"} for i, d in enumerate(values)]


island_coords = [
    [47.3331, -3.1870], [47.3700, -3.2200], [47.3900, -3.1500],
    [47.3500, -3.0700], [47.2900, -3.1200], [47.3331, -3.1870],
]
belle_base = {
    "name": "Tour de Belle-Île-en-Mer par le GR 340",
    "region": "Belle-Île-en-Mer",
    "description": "Tour côtier de Belle-Île-en-Mer sur le GR 340",
    "route_type": "Boucle",
    "duration_days": 5,
    "start": {"lat": 47.3331, "lon": -3.1870},
    "end": {"lat": 47.3331, "lon": -3.1870},
    "route_preview": {"coords": island_coords, "fallback": False, "relation_ref": "GR 340", "relation_name": "Tour de Belle-Île-en-Mer"},
    "stages": stages([17, 18, 18, 18, 19]),
    "water": [{"name": "Fontaine", "display_only": True}],
}
assert_reference("belle-ile-basic", dict(belle_base))
assert_reference("belle-ile-camping", {
    **belle_base,
    "stages": stages([17, 18, 18, 18, 19]),
    "logistics": {"mode": "route-first", "route_immutable": True, "nights_required": 4, "nights_resolved": 3, "status": "partial"},
})
assert_reference("mont-saint-michel-loop", {
    "name": "Boucle du Mont Saint-Michel", "region": "Mont Saint-Michel",
    "description": "Boucle pédestre autour du Mont Saint-Michel", "route_type": "Boucle",
    "start": {"lat": 48.6361, "lon": -1.5115}, "end": {"lat": 48.6361, "lon": -1.5115},
    "route_preview": {"coords": [[48.6361, -1.5115], [48.58, -1.45], [48.61, -1.57], [48.6361, -1.5115]], "fallback": False},
    "stages": stages([9, 21, 20, 20]), "water": [],
})
assert_reference("generic-loop-no-gr", {
    "name": "Boucle test sans GR", "region": "Chartres", "route_type": "Boucle",
    "start": {"lat": 48.4469, "lon": 1.4890}, "end": {"lat": 48.4469, "lon": 1.4890},
    "route_preview": {"coords": [[48.4469, 1.4890], [48.50, 1.60], [48.38, 1.65], [48.4469, 1.4890]], "fallback": False},
    "stages": stages([19, 20, 20, 21]), "water": [],
})
assert_reference("generic-traverse-no-gr", {
    "name": "Traversée Tours Chinon", "region": "Touraine", "route_type": "Traversée",
    "start": {"lat": 47.3941, "lon": 0.6848}, "end": {"lat": 47.1670, "lon": 0.2428},
    "route_preview": {"coords": [[47.3941, 0.6848], [47.31, 0.55], [47.24, 0.39], [47.1670, 0.2428]], "fallback": False},
    "stages": stages([17, 18, 19]), "water": [],
})

print("TrekBrain v9 stability gate: 5 reference cases + wrapper topology OK")
