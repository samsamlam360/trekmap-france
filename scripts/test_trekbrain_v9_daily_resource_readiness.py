"""Daily supplies, targeted provider budgets and honest evidence, fully offline."""
from copy import deepcopy
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import free_planner_v2 as free
from backend import trekbrain_resources_v9 as resources
from backend import trekbrain_water_discovery_v9 as water


def reference(identity, lat, kind="water", status="potable_referenced", **extra):
    return {"name": f"Resource {identity}", "lat": lat, "lon": 5.0,
            "category": kind, "status": status,
            "source_url": f"https://www.openstreetmap.org/node/{identity}", **extra}


plan = {
    "duration_days": 3,
    "route_preview": {"coords": [[45.0, 5.0], [45.2, 5.0]], "fallback": False},
    "stages": [{"day": 1, "distance_km": 3}, {"day": 2, "distance_km": 12},
               {"day": 3, "distance_km": 5}],
    "water": [reference(1, 45.015), reference(2, 45.08, status="unverified"),
              reference(3, 45.18, status="not_potable"),
              reference(4, 45.19, osm_tags={"amenity": "drinking_water", "access": "private"})],
    "food": [reference(11, 45.08, "food"),
             reference(12, 45.17, "food", source_url="https://www.openstreetmap.org.evil/node/12")],
}
geometry = deepcopy(plan["route_preview"])
missing = resources._missing_terrain_intent(plan, {"water": True, "food": True})
assert missing["missing_water_days"] == [2, 3], missing
assert missing["missing_food_days"] == [1, 3], missing
assert all(resources.confirmed_water_reference(item) is False for item in plan["water"][1:])
samples = water._missing_day_samples(plan, plan["route_preview"]["coords"], 3)
assert len(samples) <= 16 and min(point[0] for point in samples) >= 45.03, samples
assert [45.15, 5.0] in samples and [45.2, 5.0] in samples, samples

original = free._request_json
calls = []


def empty_provider(url, **kwargs):
    calls.append(kwargs)
    assert kwargs["cache_empty"] is False
    return {"elements": []}


free._request_json = empty_provider
resources._OSM_OVERPASS_FAILURES = 0
resources._OSM_OVERPASS_COOLDOWN_UNTIL = 0.0
stats = {}
try:
    assert resources._bbox_route_water_food(plan, missing, stats) == []
finally:
    free._request_json = original
assert len(calls) == 2 and all(call["retries"] == 1 for call in calls), calls
assert stats["water_days_searched"] == [2, 3] and stats["food_days_searched"] == [1, 3], stats
assert stats["status"] == "empty" and stats["responses"] == 2, stats
query = calls[0]["data"]["data"]
quotas = [int(value) for value in re.findall(r"out center tags (\d+);", query)]
assert sum(quotas[:2]) <= 90 and sum(quotas[2:]) <= 176, quotas
assert query.count('natural"="spring') == 2 and query.count('shop"~') == 2, query
assert plan["route_preview"] == geometry, "Discovery cannot change the walked geometry"

enriched = resources.enrich_resources(deepcopy(plan))
coverage = resources._resource_coverage(
    enriched, {"water": True, "food": True},
    {"status": "unavailable"}, {"status": "unavailable"},
)
assert coverage["water"] == "partial" and coverage["food"] == "partial", coverage
assert coverage["days_with_water"] == [1] and coverage["days_without_water"] == [2, 3], coverage
assert coverage["days_with_unverified_water"] == [2], coverage
assert coverage["daily"][1]["water"]["status"] == "providers_unavailable", coverage
assert coverage["daily"][0]["food"]["status"] == "providers_unavailable", coverage
enriched["map_resources"]["coverage"] = coverage
resources._annotate_stage_resources(enriched)
assert "Aucune eau potable" in enriched["stages"][1]["water_notes"], enriched["stages"]
assert "services cartographiques indisponibles" in enriched["stages"][0]["food_notes"], enriched["stages"]
assert enriched["stages"][1]["water_verification"]["status"] == "providers_unavailable"
assert enriched["route_preview"] == geometry

# An Overpass timeout may be encoded in HTTP 200 JSON, not an exception.
calls.clear()
free._request_json = lambda _url, **kwargs: calls.append(kwargs) or {"remark": "runtime timeout"}
stats = {}
try:
    assert resources._bbox_route_water_food(plan, missing, stats) == []
finally:
    free._request_json = original
assert len(calls) == 2 and stats["status"] == "unavailable" and not stats["responses"], stats
assert resources._resource_coverage(
    resources.enrich_resources({**deepcopy(plan), "water": [], "food": []}),
    {"water": True, "food": True}, stats, {"status": "unavailable"},
)["water"] == "providers_unavailable"
resources._OSM_OVERPASS_FAILURES = 0
resources._OSM_OVERPASS_COOLDOWN_UNTIL = 0.0

# Marker limits cannot invalidate genuine supplies on later walking days.
long_plan = {"duration_days": 20, "stages": [{"day": day} for day in range(1, 21)],
             "route_preview": {"coords": [[45.0, 5.0], [47.0, 5.0]]}, "water": [], "food": []}
for day in range(20):
    for index in range(3):
        lat = 45 + day * .1 + .025 + index * .005
        long_plan["water"].append(reference(1000 + day * 3 + index, lat))
        long_plan["food"].append(reference(2000 + day * 3 + index, lat, "food"))
long_plan = resources.enrich_resources(long_plan)
assert len(long_plan["map_resources"]["points"]) == 48
assert len(long_plan["map_resources"]["evidence_points"]) == 120
coverage = resources._resource_coverage(long_plan, {"water": True, "food": True})
assert coverage["water"] == coverage["food"] == "verified", coverage
assert not coverage["days_without_water"] and not coverage["days_without_food"], coverage
long_plan["map_resources"]["coverage"] = coverage
resources._annotate_stage_resources(long_plan)
assert long_plan["stages"][-1]["water_verification"]["status"] == "verified"
assert long_plan["stages"][-1]["food_verification"]["status"] == "verified"

# Several unverified springs close to the line cannot displace a drinking tap
# from the three visible water icons or from readiness evidence.
crowded = {"duration_days": 1, "route_preview": {"coords": [[45.0, 5.0], [45.1, 5.0]]},
           "water": [reference(3000 + index, 45.01 + index * .001, status="unverified")
                     for index in range(5)] + [reference(4000, 45.08)]}
crowded = resources.enrich_resources(crowded)
assert any(point["status"] == "potable_referenced" for point in crowded["map_resources"]["points"])
assert resources._resource_coverage(crowded, {"water": True})["water"] == "verified"

# Distinct sources sharing a coordinate keep independent safety labels.
collision = {"water": [reference(5000, 45.1)]}
resources._merge_supplemented_resources(collision, [reference(5001, 45.1, water_status="not_potable")])
assert len(collision["water"]) == 2 and collision["water"][0]["status"] == "potable_referenced", collision

print("Daily evidence, unknown/unsafe/private water, targeted quotas, outages and immutable geometry: PASS")
print("48-marker cap preserves full daily evidence and prioritizes referenced drinking water: PASS")
