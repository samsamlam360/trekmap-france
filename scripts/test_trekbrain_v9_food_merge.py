"""Regression: concurrent food/resource lists must both reach map and stages."""
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_resources_v9 as terrain

route = {
    "duration_days": 2,
    "route_preview": {
        "coords": [[45.0, 5.0], [45.02, 5.02], [45.04, 5.04]],
        "fallback": False,
    },
    "start": {"lat": 45.0, "lon": 5.0},
    "end": {"lat": 45.04, "lon": 5.04},
    "stages": [{"day": 1}, {"day": 2}],
    "resources": [
        {"name": "Boutique A", "category": "food", "lat": 45.01, "lon": 5.01,
         "source_url": "https://www.openstreetmap.org/node/111"},
    ],
    "food": [
        {"name": "Boutique B", "category": "food", "lat": 45.03, "lon": 5.03,
         "source_url": "https://www.openstreetmap.org/node/222"},
        {"name": "Doublon A", "category": "food", "lat": 45.01, "lon": 5.01,
         "source_url": "https://www.openstreetmap.org/node/111"},
        {"name": "Boutique hors tracé", "category": "food", "lat": 46.1, "lon": 6.1,
         "source_url": "https://www.openstreetmap.org/node/333"},
    ],
}
base_rows = terrain._food_candidates(route)
assert len(base_rows) == 3, base_rows
assert {"Boutique A", "Boutique B"} <= {item["name"] for item in base_rows}
assert terrain._missing_terrain_intent(route, {"food": True, "water": False})["food"] is False

mapped = terrain.enrich_resources(deepcopy(route))
foods = [p for p in mapped["map_resources"]["points"] if p["kind"] == "food"]
assert len(foods) == 2, foods
assert {p["source_url"] for p in foods} == {
    "https://www.openstreetmap.org/node/111",
    "https://www.openstreetmap.org/node/222",
}, foods
assert mapped["map_resources"]["counts"]["food"] == 2, mapped["map_resources"]

terrain._annotate_stage_resources(mapped)
assert any("Boutique A" in (s.get("food_notes") or "") for s in mapped["stages"]), mapped["stages"]
assert any("Boutique B" in (s.get("food_notes") or "") for s in mapped["stages"]), mapped["stages"]

new = terrain._merge_supplemented_resources(deepcopy(route), [
    {"name": "Boutique C", "category": "food", "lat": 45.025, "lon": 5.025,
     "source_url": "https://www.openstreetmap.org/node/444"}
])
names = {x["name"] for x in terrain._food_candidates(new)}
assert {"Boutique A", "Boutique B", "Boutique C"} <= names, names
assert len([x for x in terrain.enrich_resources(new)["map_resources"]["points"] if x["kind"] == "food"]) == 3

# A failed public POI lookup must never look like a guaranteed absence
# of supplies. The same evidence label must be visible on daily stage cards.
missing_food = {"map_resources": {"points": [], "coverage": {
    "food": "providers_unavailable",
}}, "stages": [{"day": 1}, {"day": 2}]}
terrain._annotate_stage_resources(missing_food)
assert all("indisponibles" in stage["food_notes"] for stage in missing_food["stages"])

not_verified = {"map_resources": {"points": [], "coverage": {
    "food": "not_verified",
}}, "stages": [{"day": 1}]}
terrain._annotate_stage_resources(not_verified)
assert "Aucun commerce vérifié" in not_verified["stages"][0]["food_notes"]

print("Both food resource fields preserved, sourced and rendered per day: PASS")
