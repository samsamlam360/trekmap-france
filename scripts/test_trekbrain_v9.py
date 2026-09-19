"""Offline regression tests for TrekBrain v9 precision logic."""
from backend.free_planner_v2 import AIPlanRequest
from backend.smart_planner_v9 import precision_audit
from backend.web_research_v9 import source_score

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
    "route_preview": {"fallback": False, "distance_km": 64},
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

trusted = source_score({"url": "https://www.example.gouv.fr/agenda", "title": "Agenda randonnée Vercors", "snippet": "Informations officielles randonnée Vercors 2026"}, "agenda randonnée Vercors")
social = source_score({"url": "https://www.instagram.com/example", "title": "Vercors", "snippet": "Photo randonnée"}, "agenda randonnée Vercors")
assert trusted > social, (trusted, social)

print("TrekBrain v9 precision tests: OK")
print("good=", good["score"], "bad=", bad["score"], "trusted=", trusted, "social=", social)
