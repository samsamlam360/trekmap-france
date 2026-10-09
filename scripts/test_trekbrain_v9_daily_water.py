"""Unnamed water and first-visit daily gaps must survive provider failures."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import smart_planner_v3 as planner
from backend import trekbrain_resources_v9 as resources

plan = {"duration_days": 3, "stages": [{"day": d} for d in (1, 2, 3)],
        "route_preview": {"coords": [[45+i*.05, 5] for i in range(4)]}, "water": []}
def point(i):
    return {"lat": 45.025+i*.05, "lon": 5, "category": "water",
            "source_url": f"https://www.openstreetmap.org/node/{i+1}"}
for count in range(4):
    plan["water"] = [point(i) for i in range(count)]
    assert resources._missing_terrain_intent(plan, {"water": True})["water"] == (count < 3)
plan["water"] = [{**point(i), "source_url": ""} for i in range(3)]
assert resources._missing_terrain_intent(plan, {"water": True})["water"]
assert not resources._missing_terrain_intent(plan, {"water": False})["water"]

old = planner._request_json
calls = []
def reverse(url, **kwargs):
    calls.append((url, kwargs))
    assert url.endswith('/reverse') and 'q' not in kwargs['params']
    assert kwargs['params']['radius'] <= 5.5 and kwargs['cache_empty'] is False
    assert 'amenity:drinking_water' in kwargs['params']['osm_tag']
    return {"features": [{"properties": {"osm_type": "N", "osm_id": 222,
             "osm_key": "amenity", "osm_value": "drinking_water", "countrycode": "FR"},
             "geometry": {"coordinates": [5, 45.001]}}]}
planner._request_json = reverse
try:
    result = planner._photon_anchor_resource({"lat":45,"lon":5}, 'water',
        ('amenity:drinking_water','natural:spring','man_made:water_tap'),5.5)
    assert result and result['water_status'] == 'potable_referenced'
    assert result['source_url'].endswith('/222') and len(calls) == 1
    def unavailable(*args, **kwargs):
        raise RuntimeError('provider unavailable')
    planner._request_json = unavailable
    assert planner._photon_anchor_resource({'lat':45,'lon':5},'water',('amenity:drinking_water',),5.5) is None
finally:
    planner._request_json = old

old_lookup = planner._photon_anchor_resource
seen=[]
planner._photon_anchor_resource = lambda p, kind, tags, radius: seen.append((p,kind))
try:
    # One day still has water probes. A closed loop spends no duplicate slot.
    planner._postroute_corridor_resources([point(0),point(0)], {'water':True}, [])
    assert len(seen) == 1, seen
    seen.clear()
    bounds=[{'lat':45+i*.1,'lon':5} for i in range(9)]
    planner._postroute_corridor_resources(bounds, {'water':True,'food':True,'sleep':True,'transit':True}, [])
    assert len(seen) <= 6 and {'water','food','stay','transit'} <= {kind for _,kind in seen},seen
finally:
    planner._photon_anchor_resource = old_lookup
# New-region regression: long routes must distribute OSM water quotas
# along the walked line without extra provider requests. A non-potable
# spring stays visible but does NOT count as drinking-water coverage.
from backend import free_planner_v2 as free
long_plan = {
    "duration_days": 6,
    "stages": [{"day": i} for i in range(1, 7)],
    "route_preview": {"coords": [[45 + i * 0.06, 5] for i in range(8)]},
    "water": [],
    "accommodations": [],
}
old_request = free._request_json
captured = []
def fake_osm_water(url, **kwargs):
    query = kwargs["data"]["data"]
    captured.append(query)
    assert query.count("out center tags 36;") == 6, query
    assert query.count("(around:4500,") == 18, query
    assert "out center tags 220;" not in query
    assert kwargs["cache_empty"] is False
    return {"elements": [
        {"type": "node", "id": 10001, "lat": 45.005, "lon": 5.0,
         "tags": {"amenity": "drinking_water", "name": "Fontaine au départ"}},
        {"type": "node", "id": 10002, "lat": 45.37, "lon": 5.0,
         "tags": {"natural": "spring", "drinking_water": "no",
                  "name": "Source non potable"}},
    ]}
free._request_json = fake_osm_water
try:
    diagnostics = {}
    found_water = resources._bbox_route_water_food(
        long_plan, {"water": True}, diagnostics
    )
finally:
    free._request_json = old_request
assert len(captured) == 1, captured
assert diagnostics["water_segments"] == 6, diagnostics
assert diagnostics["attempts"] == 1, diagnostics
assert len(found_water) == 2, found_water
assert {w["water_status"] for w in found_water} == {
    "potable_referenced", "not_potable"
}, found_water

# A fresh "drinking_water=no" must override the same source previously
# cached as potable, rather than disappearing during deduplication.
stale = {
    **long_plan,
    "water": [{
        **found_water[1], "status": "potable_referenced",
        "water_status": "potable_referenced",
        "notes": "Potable selon les anciennes données",
    }],
}
resources._merge_supplemented_resources(stale, [found_water[1]])
assert len(stale["water"]) == 1, stale["water"]
assert stale["water"][0]["status"] == "not_potable", stale["water"]
assert "ne pas boire" in stale["water"][0]["notes"], stale["water"]

only_unsafe = {**long_plan, "water": [found_water[1]]}
assert resources._missing_terrain_intent(
    only_unsafe, {"water": True}
)["water"] is True
display_plan = resources.enrich_resources(
    {**long_plan, "water": found_water}
)
water_points = [
    item for item in display_plan["map_resources"]["points"]
    if item["kind"] == "water"
]
assert {p["status"] for p in water_points} == {
    "potable_referenced", "not_potable"
}, water_points
assert any(
    p["status"] == "not_potable" and "ne pas boire" in p["notes"]
    for p in water_points
), water_points
assert resources._sourced_water_coverage(water_points) == ([1], 1), water_points
assert resources._sourced_water_coverage([{
    "kind": "water",
    "status": "not_potable",
    "route_day": 3,
    "source_url": "https://www.openstreetmap.org/node/9999",
}]) == ([], 0)
resources._annotate_stage_resources(display_plan)
assert "potable référencée" in display_plan["stages"][0]["water_notes"]
assert any(
    "non potable" in stage["water_notes"]
    and "Aucune eau potable" in stage["water_notes"]
    for stage in display_plan["stages"]
), display_plan["stages"]
assert any(
    "Aucun point d'eau OSM confirmé" in stage["water_notes"]
    for stage in display_plan["stages"]
), display_plan["stages"]

# One-day routes retain the cheap legacy bbox rather than the segmented
# search and do not increase the cost of the common short hike.
short_plan = {
    **long_plan,
    "duration_days": 1,
    "stages": [{"day": 1}],
    "route_preview": {"coords": long_plan["route_preview"]["coords"][:2]},
}
seen_short = []
free._request_json = lambda _url, **kwargs: (
    seen_short.append(kwargs["data"]["data"]) or {"elements": []}
)
try:
    resources._bbox_route_water_food(short_plan, {"water": True})
finally:
    free._request_json = old_request
assert seen_short and "out center tags 90;" in seen_short[0], seen_short
assert "out center tags 36;" not in seen_short[0], seen_short

print('Daily water: source evidence, 6-stage quota fairness, potability safety, warnings, and bounded calls: PASS')
