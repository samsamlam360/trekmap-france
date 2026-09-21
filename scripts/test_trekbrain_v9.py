"""Offline regression tests for TrekBrain v9 precision logic."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.free_planner_v2 import AIPlanRequest
from backend.smart_planner_v9 import precision_audit
from backend.web_research_v9 import source_score
from backend import trekbrain_request_v9 as request_reconcile
from backend.trekbrain_request_overlay_v9 import _effective_payload

request = AIPlanRequest(
    prompt="Je veux une boucle de 4 jours, 16 km par jour, avec eau et camping",
    region="Vercors",
    days=4,
    daily_km=16,
    difficulty="medium",
    route_type="Boucle",
    require_transit=False,
    require_water=True,
    require_accommodation=True,
    require_food=False,
)

features = {"water": 1.0, "sleep": 1.0, "camping": 1.0, "loop": 1.0}
research = {"results": [], "evidence": {"results": 0, "strong_results": 0, "mean_score": 0}}
compound = {"side_requests": []}

base = {
    "confidence": {"score": 92, "limitations": []},
    "route_preview": {"fallback": False, "distance_km": 64, "coords": [[44.97, 5.55], [44.971, 5.551]]},
    "start": {"lat": 44.97, "lon": 5.55},
    "end": {"lat": 44.971, "lon": 5.551},
    "stages": [
        {"distance_km": 15.5, "overnight": "Camping A", "water_notes": "Fontaine (potable référencée)"},
        {"distance_km": 16.5, "overnight": "Camping B", "water_notes": "Source (potabilité non confirmée)"},
        {"distance_km": 16.0, "overnight": "Camping C", "water_notes": "Fontaine (potable référencée)"},
        {"distance_km": 16.0, "overnight": "Fin du trek", "water_notes": "Fontaine (potable référencée)"},
    ],
    "duration_days": 4,
    "water": [{"status": "potable_referenced"}, {"status": "potable_referenced"}],
    "accommodations": [{"name": "Camping A"}],
    "transport": {},
    "side_requests": [],
}

good = precision_audit(base, request, features, research, compound)
assert good["score"] >= 80, good
assert not good["blockers"], good

broken = dict(base)
broken["end"] = {"lat": 45.20, "lon": 5.90}
broken["stages"] = [
    {"distance_km": 7, "overnight": "Nuitée à confirmer", "water_notes": "Aucun point d'eau cartographié trouvé à proximité de l'étape."},
    {"distance_km": 29, "overnight": "Nuitée à confirmer", "water_notes": "Aucun point d'eau cartographié trouvé à proximité de l'étape."},
    {"distance_km": 8, "overnight": "Nuitée à confirmer", "water_notes": "Aucun point d'eau cartographié trouvé à proximité de l'étape."},
]
broken["duration_days"] = 3
bad = precision_audit(broken, request, features, research, compound)
assert bad["score"] < good["score"] - 20, (good, bad)
assert bad["blockers"], bad

transit_request = request.model_copy(update={"require_transit": True})
missing_transit = precision_audit(base, transit_request, {**features, "transit": 1.0}, research, compound)
assert "accès en transport non renseigné" in missing_transit["blockers"], missing_transit

missing_water_plan = dict(base)
missing_water_plan["stages"] = [dict(stage, water_notes="") for stage in base["stages"]]
missing_water = precision_audit(missing_water_plan, request, features, research, compound)
water_check = next(item for item in missing_water["checks"] if item["name"] == "Eau")
assert water_check["status"] == "unknown", missing_water

trusted = source_score({"url": "https://www.example.gouv.fr/agenda", "title": "Agenda randonnée Vercors", "snippet": "Informations officielles randonnée Vercors 2026"}, "agenda randonnée Vercors")
social = source_score({"url": "https://www.instagram.com/example", "title": "Vercors", "snippet": "Photo randonnée"}, "agenda randonnée Vercors")
assert trusted > social, (trusted, social)

# Regression from the mobile advisor: the text asks for four days around the
# Mont-Saint-Michel while the form still contains Belle-Ile / five days from a
# previous request. The written request must win instead of creating an
# impossible cross-region constraint set.
real_geocode = request_reconcile.geo._geocode

def fake_geocode(query):
    q = request_reconcile._fold(query)
    if "mont saint-michel" in q or "mont st michel" in q:
        return [{"name": "Mont Saint-Michel", "short_name": "Mont Saint-Michel", "lat": 48.636, "lon": -1.511}]
    if "belle-ile" in q or "belle ile" in q:
        return [{"name": "Belle-Ile-en-Mer", "short_name": "Belle-Ile-en-Mer", "lat": 47.326, "lon": -3.170}]
    if "vercors" in q:
        return [{"name": "Vercors", "short_name": "Vercors", "lat": 44.970, "lon": 5.550}]
    if "grenoble" in q:
        return [{"name": "Grenoble", "short_name": "Grenoble", "lat": 45.188, "lon": 5.724}]
    return []

request_reconcile.geo._geocode = fake_geocode
try:
    stale = AIPlanRequest(
        prompt=(
            "Je souhaite faire un trek de 4 jours et je veux visiter le mont st Michel "
            "un soir après la randonnée. Je veux que ce soit une boucle et je veux des campings tous les jours"
        ),
        region="Belle-Île en mer",
        days=5,
        daily_km=18,
        difficulty="medium",
        route_type="Boucle",
        require_transit=True,
        require_water=True,
        require_accommodation=True,
        require_food=True,
    )
    effective, resolution = _effective_payload(stale)
    assert effective.region == "Mont Saint-Michel", (effective.region, resolution)
    assert effective.days == 4, effective
    assert effective.route_type == "Boucle", effective
    # An evening visit after the day's hike identifies the right area but must
    # not become a mandatory walking waypoint. That distinction is what keeps
    # the ORS round-trip recovery usable.
    assert "passer par Mont Saint-Michel" not in effective.prompt, effective.prompt
    assert resolution["forced_waypoint"] is None, resolution
    assert "Mont Saint-Michel" in resolution["after_trip_places"], resolution
    assert resolution["region_overridden"] is True, resolution
    assert resolution["reason"] == "stale-form-region-conflict", resolution

    # An explicitly stated trek area remains authoritative when another place is
    # merely an activity after the trip.
    explicit = stale.model_copy(update={
        "prompt": "Je fais un trek dans le Vercors puis je veux visiter Grenoble après le trek",
        "region": "Vercors",
        "days": 3,
    })
    effective2, resolution2 = _effective_payload(explicit)
    assert effective2.region == "Vercors", (effective2.region, resolution2)
    assert resolution2["region_overridden"] is False, resolution2
finally:
    request_reconcile.geo._geocode = real_geocode

# The geographic gate is part of the mandatory precision suite so a future
# routing refactor cannot reintroduce direct lines across water unnoticed.
runpy.run_path(str(ROOT / "scripts" / "test_trekbrain_v9_geo_safety.py"), run_name="__trekbrain_geo_safety__")

print("TrekBrain v9 precision tests: OK")
print("good=", good["score"], "bad=", bad["score"], "trusted=", trusted, "social=", social)
