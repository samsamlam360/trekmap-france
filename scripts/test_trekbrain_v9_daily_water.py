"""Unnamed water and first-visit daily gaps must survive provider failures."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import smart_planner_v3 as planner
from backend import trekbrain_resources_v9 as resources

plan = {"duration_days": 3, "stages": [{"day": d} for d in (1, 2, 3)],
        "route_preview": {"coords": [[45+i*.05, 5] for i in range(4)]}, "water": []}
def point(i):
    return {"lat": 45.025+i*.05, "lon": 5, "category": "water", "water_status": "potable_referenced",
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
# Regression: preserve a real mapped source on the map without pretending
# drinking_water=no meets the overnight drinking-water requirement.
unsafe_plan = {
    "duration_days": 2,
    "stages": [{"day": 1}, {"day": 2}],
    "route_preview": {"coords": [[45.0, 5.0], [45.05, 5.0], [45.10, 5.0]]},
    "water": [
        {"name": "Fontaine potable", "lat": 45.02, "lon": 5.0,
         "water_status": "potable_referenced",
         "source_url": "https://www.openstreetmap.org/node/9101"},
        {"name": "Source à ne pas boire", "lat": 45.08, "lon": 5.0,
         "water_status": "not_potable",
         "source_url": "https://www.openstreetmap.org/node/9102"},
    ],
    "accommodations": [],
}
assert resources._missing_terrain_intent(
    unsafe_plan, {"water": True}
)["water"] is True
display = resources.enrich_resources(unsafe_plan)
water_map = [p for p in display["map_resources"]["points"] if p["kind"] == "water"]
assert len(water_map) == 2, water_map
assert resources._sourced_water_coverage(water_map) == ([1], 1), water_map
assert any(
    p["status"] == "not_potable" and "ne pas boire" in p["notes"]
    for p in water_map
), water_map
resources._annotate_stage_resources(display)
assert "Aucune eau potable" in display["stages"][1]["water_notes"], display["stages"]

# A newer non-potable OSM record must take precedence over a stale cached
# "potable" record at the same node, even when coordinates are identical.
stale_plan = {
    **unsafe_plan,
    "water": [{
        **unsafe_plan["water"][1],
        "water_status": "potable_referenced", "status": "potable_referenced",
        "notes": "Ancien état",
    }],
}
resources._merge_supplemented_resources(stale_plan, [unsafe_plan["water"][1] | {"category": "water"}])
assert len(stale_plan["water"]) == 1
assert stale_plan["water"][0]["status"] == "not_potable", stale_plan["water"]
assert "ne pas boire" in stale_plan["water"][0]["notes"]

# Route-first logistics preloads water before the final resource overlay.
# The same OSM source can already be present as "potable" from old data.
# New drinking_water=no evidence must NOT be discarded by coord dedup.
from backend import trekbrain_route_logistics_v9 as lodging
old_source = {
    "name": "Source du sentier", "lat": 45.08, "lon": 5.0,
    "water_status": "potable_referenced", "status": "potable_referenced",
    "source_url": "https://www.openstreetmap.org/node/9102",
    "notes": "Old potable",
}
preload_plan = {"water": [old_source], "resources": [], "points_of_interest": []}
unsafe_row = {
    "category": "water", "water_status": "not_potable",
    "lat": 45.08, "lon": 5.0,
    "source_url": "https://www.openstreetmap.org/node/9102",
}
lodging._attach_preloaded_terrain(preload_plan, [unsafe_row], True)
assert len(preload_plan["water"]) == 1, preload_plan["water"]
assert preload_plan["water"][0]["status"] == "not_potable", preload_plan
assert "ne pas boire" in preload_plan["water"][0]["notes"], preload_plan

# OSM geometry may move by a few metres between observations while the
# OSM source ID stays unchanged; identity must beat rounded coordinates.
shifted_old = {**old_source, "lat": 45.0798, "status": "potable_referenced"}
shifted_plan = {"water": [shifted_old], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(shifted_plan, [unsafe_row], True)
assert len(shifted_plan["water"]) == 1, shifted_plan["water"]
assert shifted_plan["water"][0]["status"] == "not_potable", shifted_plan

fresh_plan = {"water": [], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(fresh_plan, [unsafe_row], True)
assert fresh_plan["water"][0]["status"] == "not_potable", fresh_plan
assert "ne pas boire" in fresh_plan["water"][0]["notes"], fresh_plan

# The exact source identity guards against mistakenly marking a distinct
# source at the same coordinate as non-potable.
other_source = {
    **old_source, "source_url": "https://www.openstreetmap.org/node/9999",
}
different_plan = {"water": [other_source], "resources": [], "points_of_interest": []}
lodging._attach_preloaded_terrain(different_plan, [unsafe_row], True)
assert different_plan["water"][0]["status"] == "potable_referenced", different_plan
# Every other discovery endpoint continues to use its old bounded query;
# this test does not open any network connection.
# A real OSM object can carry contradictory tags. The explicit water safety
# label always wins over the generic amenity=drinking_water hint, at both
# route-first discovery and the shared v3 Overpass parser.
conflicting = {
    "type": "node", "id": 990011, "lat": 45.04, "lon": 5.0,
    "tags": {"amenity": "drinking_water", "drinking_water": "no", "name": "Fontaine condamnée"},
}
safe = {
    "type": "node", "id": 990012, "lat": 45.06, "lon": 5.0,
    "tags": {"amenity": "drinking_water", "drinking_water": "yes"},
}
unknown = {
    "type": "node", "id": 990013, "lat": 45.08, "lon": 5.0,
    "tags": {"natural": "spring"},
}
assert lodging._terrain_resource(conflicting)["water_status"] == "not_potable"
assert lodging._terrain_resource(safe)["water_status"] == "potable_referenced"
assert lodging._terrain_resource(unknown)["water_status"] == "unverified"

real_overpass = planner._overpass
try:
    planner._overpass = lambda _query, **_kwargs: {
        "elements": [conflicting, safe, unknown]
    }
    checked, _extras, _notes = planner._combined_nearby(
        {"lat": 45.0, "lon": 5.0}, 5.0, ["water"]
    )
finally:
    planner._overpass = real_overpass
status_by_id = {x["source_url"].rsplit("/", 1)[-1]: x["water_status"] for x in checked}
assert status_by_id["990011"] == "not_potable", status_by_id
assert status_by_id["990012"] == "potable_referenced", status_by_id
assert status_by_id["990013"] == "unverified", status_by_id
print("Contradictory OSM water tags: explicit not-potable precedence: PASS")

print("Non-potable source isolation and stale-cache safety: PASS")

print('Daily water: partial/complete/unsourced, unnamed reverse search, outage, one-day and bounded wave: PASS')


# Phase 1 cold regions: Photon's single filtered reverse answer may contain
# an unknown spring closer than an explicitly documented drinking fountain.
# It must prefer documented public drinking water without claiming an unknown
# source has become potable, even if Overpass is unavailable.
def photon_feature(identifier, lat, tag_key, tag_value, extra=None):
    props={"osm_type":"N","osm_id":identifier,"countrycode":"FR",
           "osm_key":tag_key,"osm_value":tag_value}
    if extra is not None:
        props["extra"]=extra
    return {"properties":props,"geometry":{"coordinates":[5.0,lat]}}
anchor={"lat":45.0,"lon":5.0}
def fake_water_reply(url,**kwargs):
    assert url.endswith("/reverse") and kwargs["params"]["limit"]==20
    return {"features":[
        photon_feature(92001,45.001,"natural","spring"),
        photon_feature(92002,45.002,"amenity","drinking_water",
                       {"access":"private"}),
        photon_feature(92003,45.005,"amenity","drinking_water"),
    ]}
old_request=planner._request_json
planner._request_json=fake_water_reply
try:
    chosen=planner._photon_anchor_resource(
        anchor,"water",("natural:spring","amenity:drinking_water"),5.5)
finally:
    planner._request_json=old_request
from backend.trekbrain_water_evidence_v9 import confirmed_water_reference
assert chosen and chosen["source_url"].endswith("/92003"),chosen
assert confirmed_water_reference(chosen),chosen

# A private drinking fountain on its own is still mapped context but must
# NOT satisfy the days-with-drinking-water readiness requirement.
planner._request_json=lambda url,**kwargs: {"features":[
    photon_feature(92002,45.002,"amenity","drinking_water",
                   {"access":"private"}),
]}
try:
    restricted=planner._photon_anchor_resource(
        anchor,"water",("amenity:drinking_water",),5.5)
finally:
    planner._request_json=old_request
assert restricted["osm_tags"]["access"]=="private"
assert not confirmed_water_reference(restricted),restricted

# Original six-call provider cap retained: share remaining free requests
# across at least two DISTINCT days of unsolved potable water rather than
# spending the penultimate slot on a redundant second transit station.
route_anchors=[
    {"lat":45.0+i*.06,"lon":5.0,"category":"route_anchor",
     "name":f"J{i}"} for i in range(4)
]
checked=[]
old_probe=planner._photon_anchor_resource
planner._photon_anchor_resource=lambda point,category,tags,radius: (
    checked.append((round(point["lat"],4),category)) or None
)
try:
    planner._postroute_corridor_resources(route_anchors,{
        "food":True,"water":True,"sleep":True,"transit":True,
        "accommodation":"camping"
    },[{"category":"water","lat":45.0,"lon":5.0,
        "source_url":"https://www.openstreetmap.org/node/92004",
        "osm_tags":{"natural":"spring"},"water_status":"unverified"}])
finally:
    planner._photon_anchor_resource=old_probe
assert len(checked)==6,checked
assert [category for _,category in checked].count("food")==2,checked
water_locations={lat for lat,category in checked if category=="water"}
assert water_locations=={45.0,45.06},checked
assert {"stay","transit"} <= {kind for _,kind in checked},checked
# Daily labels must not suggest private drinking water is public water.
private_stage={
    "duration_days":1,"stages":[{"day":1}],
    "route_preview":{"coords":[[45.0,5.0],[45.06,5.0]]},
    "water":[restricted],
}
resources.enrich_resources(private_stage)
resources._annotate_stage_resources(private_stage)
assert "accès ou disponibilité restreints" in private_stage["stages"][0]["water_notes"],private_stage
assert "Aucune eau potable identifiée" in private_stage["stages"][0]["water_notes"],private_stage

# Explicit nonpotability encoded in Photon's optional extra metadata wins
# over the generic amenity=drinking_water principal tag.
planner._request_json=lambda url,**kwargs: {"features":[
    photon_feature(92009,45.003,"amenity","drinking_water",
                   {"drinking_water":"no"}),
]}
try:
    unsafe_photon=planner._photon_anchor_resource(
        anchor,"water",("amenity:drinking_water",),5.5)
finally:
    planner._request_json=old_request
assert unsafe_photon["water_status"]=="not_potable",unsafe_photon
assert not confirmed_water_reference(unsafe_photon)
print("Cold-cache Photon fallback: unknown/private springs do not hide public water; two days probed in six-call cap: PASS")


# Route-relative cold water probes must cover the WHOLE walked day, not just
# the start/night boundary of a 15-20 km route. All tests are offline and do
# not claim any fountain exists until a provider supplies an OSM object.
walk={
    "duration_days": 3,
    "stages": [
        {"distance_km":10.0},{"distance_km":20.0},{"distance_km":10.0},
    ],
    "route_preview":{"coords":[[45.0,5.0],[45.1,5.0],
                             [45.3,5.0],[45.4,5.0]]},
}
original_geometry=[point[:] for point in walk["route_preview"]["coords"]]
probes=resources._cold_water_stage_probes(walk,3,[1,2,3])
assert [p["route_day"] for p in probes]==[1,3,2],probes
assert all(p["category"]=="route_anchor" for p in probes)
assert abs(probes[0]["lat"]-45.05)<0.001,probes
assert abs(probes[1]["lat"]-45.35)<0.001,probes
assert abs(probes[2]["lat"]-45.20)<0.001,probes
assert walk["route_preview"]["coords"]==original_geometry
assert [p["route_day"] for p in resources._cold_water_stage_probes(walk,3,[2])]==[2]
assert resources._cold_water_stage_probes({"route_preview":{"coords":[]}},3,[1])==[]

# Keep the cap of six; two-day requests now check both walking-day middles.
two_days={
    "duration_days":2,
    "stages":[{"distance_km":16},{"distance_km":16}],
    "route_preview":{"coords":[[45.0,5.0],[45.08,5.0],
                               [45.16,5.0],[45.24,5.0],
                               [45.32,5.0]]},
}
water_anchors=resources._cold_water_stage_probes(two_days,2,[1,2])
assert len(water_anchors)==2
assert abs(water_anchors[0]["lat"]-45.08)<0.0001,water_anchors
assert abs(water_anchors[1]["lat"]-45.24)<0.0001,water_anchors
checked=[]
orig=planner._photon_anchor_resource
planner._photon_anchor_resource=lambda point,kind,tags,radius: (
    checked.append((kind,point["lat"])) or None
)
try:
    planner._postroute_corridor_resources(
        [{"lat":45.0,"lon":5.0},{"lat":45.16,"lon":5.0},
         {"lat":45.32,"lon":5.0}],
        {"water":True,"food":True,"sleep":True,"transit":True,
         "accommodation":"camping","_water_corridor_anchors":water_anchors},[],
    )
finally:
    planner._photon_anchor_resource=orig
assert len(checked)<=6,checked
assert [(kind,round(lat,2)) for kind,lat in checked if kind=="water"]==[
    ("water",45.08),("water",45.24)],checked
assert {"food","stay","transit"} <= {kind for kind,_ in checked},checked
print("Midstage source-water probes: real route fractions, day coverage, 6-call cap, no geometry changes: PASS")


# Cold-cache fallback: a real OSM supermarket can be presented as a POSSIBLE
# place to buy water in bottles, NEVER as a drinking fountain or complete
# water-day verification. An unknown bakery, private shop or guessed store
# must never qualify even for this secondary purchasing hint.
shopping_plan={
    "duration_days":2,
    "stages":[{"day":1},{"day":2}],
    "route_preview":{"coords":[[45.0,5.0],[45.05,5.0],[45.1,5.0]]},
    "water":[],
    "food":[
        {"name":"Épicerie du bourg","lat":45.025,"lon":5.0,
         "category":"food","source_url":"https://www.openstreetmap.org/node/880101",
         "osm_tags":{"shop":"convenience"}},
        {"name":"Boulangerie","lat":45.027,"lon":5.0,
         "category":"food","source_url":"https://www.openstreetmap.org/node/880102",
         "osm_tags":{"shop":"bakery"}},
        {"name":"Épicerie privée","lat":45.028,"lon":5.0,
         "category":"food","source_url":"https://www.openstreetmap.org/node/880103",
         "osm_tags":{"shop":"supermarket","access":"private"}},
        {"name":"Épicerie inventée","lat":45.029,"lon":5.0,
         "category":"food","source_url":"","osm_tags":{"shop":"supermarket"}},
    ],
}
resources.enrich_resources(shopping_plan)
coverage=resources._resource_coverage(shopping_plan,{"water":True,"food":True})
assert coverage["water"]=="not_verified",coverage
assert coverage["days_with_water"]==[],coverage
assert coverage["days_with_possible_bottled_water_purchase"]==[1],coverage
assert coverage["possible_bottled_water_shop_points"]==1,coverage
assert coverage["daily"][0]["water"]["possible_bottled_water_shops"]==1,coverage
assert coverage["daily"][1]["water"]["possible_bottled_water_shops"]==0,coverage
shopping_plan["map_resources"]["coverage"]=coverage
resources._annotate_stage_resources(shopping_plan)
stage=shopping_plan["stages"][0]
assert stage["water_verification"]["status"]=="not_verified",stage
assert "Épicerie du bourg" in stage["water_notes"],stage
assert "ne remplace pas" in stage["water_notes"],stage
assert stage["water_purchase_alternatives"]==[{
    "name":"Épicerie du bourg",
    "source_url":"https://www.openstreetmap.org/node/880101",
    "distance_to_route_km":0.0,"availability":"to_check"
}],stage
assert shopping_plan["stages"][1]["water_purchase_alternatives"]==[]
assert resources._potential_bottled_water_shop(shopping_plan["food"][1]) is False
print("Uncached stores: possible bottled-water purchase shown only as unverified fallback; drinking-water readiness unchanged: PASS")


# Villages may bias the EXISTING six-call Photon search, but they are not
# proof of a fountain. Only a sourced OSM place on the same walking day
# and close to the actual polyline is eligible for that geographic bias.
sourced_village={
    "name":"Vrai bourg du jour 1","lat":45.105,"lon":5.0,
    "source_url":"https://www.openstreetmap.org/node/770101",
    "osm_tags":{"place":"village"},
}
fake_city={
    "name":"Ville inventée","lat":45.081,"lon":5.0,
    "source_url":"","osm_tags":{"place":"city"},
}
offroute_town={
    "name":"Ville trop éloignée du sentier","lat":45.09,"lon":5.12,
    "source_url":"https://www.openstreetmap.org/node/770102",
    "osm_tags":{"place":"town"},
}
next_day_town={
    "name":"Ville début deuxième jour","lat":45.175,"lon":5.0,
    "source_url":"https://www.openstreetmap.org/node/770103",
    "osm_tags":{"place":"city"},
}
walk_with_villages={
    **two_days,
    "points_of_interest":[fake_city,offroute_town,sourced_village,next_day_town],
}
unmodified_geometry=[x[:] for x in two_days["route_preview"]["coords"]]
village_probes=resources._cold_water_stage_probes(walk_with_villages,2,[1,2])
assert [p["route_day"] for p in village_probes]==[1,2],village_probes
assert abs(village_probes[0]["lat"]-45.105)<0.00001,village_probes
assert village_probes[0]["name"]=="Repère eau jour 1",village_probes
assert abs(village_probes[1]["lat"]-45.24)<0.00001,village_probes
assert walk_with_villages["route_preview"]["coords"]==unmodified_geometry
assert abs(resources._cold_water_stage_probes(
    {**two_days,"points_of_interest":[fake_city,offroute_town]},2,[1]
)[0]["lat"]-45.08)<0.00001
assert abs(resources._cold_water_stage_probes(
    {**two_days,"points_of_interest":[next_day_town]},2,[1]
)[0]["lat"]-45.08)<0.00001
print("Water village probes: OSM identity, same walked day, max route deviation and no geometry mutation: PASS")


# In truly cold regions, real OSM grocery POIs are more common than mapped
# place=village objects. Use a public, source-linked shop as the same bounded
# water-search bias, but never mark it as a potable drinking-water source.
public_shop={"name":"Epicerie chemin","lat":45.107,"lon":5.0,
 "category":"food","osm_tags":{"shop":"convenience"},
 "source_url":"https://www.openstreetmap.org/node/770200"}
private_shop={**public_shop,"lat":45.081,
 "osm_tags":{"shop":"convenience","access":"private"},
 "source_url":"https://www.openstreetmap.org/node/770201"}
shop_probes=resources._cold_water_stage_probes(
    {**two_days,"food":[private_shop,public_shop]},2,[1,2])
assert abs(shop_probes[0]["lat"]-45.107)<0.00001,shop_probes
assert abs(shop_probes[1]["lat"]-45.24)<0.00001,shop_probes
assert resources._cold_water_stage_probes(
    {**two_days,"food":[private_shop]},2,[1])[0]["name"]=="Milieu du jour 1"
assert resources._sourced_water_coverage([
    {"kind":"water","route_day":1,**public_shop}])==([],0)
print("Sourced groceries may bias fountain search; private shops cannot, and neither validates drinking water: PASS")


# A SINGLE Photon lookup may return several usable OSM POIs on different
# walking stages. Never throw away the extra already-downloaded evidence.
# Nothing in this test uses the public provider or additional network calls.
extra_http=[]
def multi_photon(url,**kw):
    extra_http.append((url,kw))
    if url.endswith("/reverse"):
        return {"features":[
            {"properties":{"osm_type":"N","osm_id":982001,"countrycode":"FR",
                "osm_key":"amenity","osm_value":"drinking_water"},
             "geometry":{"coordinates":[5.0,45.020]}},
            {"properties":{"osm_type":"N","osm_id":982002,"countrycode":"FR",
                "osm_key":"amenity","osm_value":"drinking_water"},
             "geometry":{"coordinates":[5.0,45.080]}},
            {"properties":{"osm_type":"N","osm_id":982003,"countrycode":"FR",
                "osm_key":"amenity","osm_value":"drinking_water",
                "extra":{"drinking_water":"no"}},
             "geometry":{"coordinates":[5.0,45.060]}},
            {"properties":{"osm_type":"N","osm_id":982004,"countrycode":"FR",
                "osm_key":"natural","osm_value":"spring"},
             "geometry":{"coordinates":[5.0,45.055]}},
            {"properties":{"osm_type":"N","osm_id":982005,"countrycode":"FR",
                "osm_key":"amenity","osm_value":"drinking_water"},
             "geometry":{"coordinates":[5.0,45.250]}}, # Too far; reject
        ]}
    return {"features":[
        {"properties":{"osm_type":"N","osm_id":982101,"countrycode":"FR",
            "osm_key":"shop","osm_value":"bakery"},
         "geometry":{"coordinates":[5.0,45.030]}},
        {"properties":{"osm_type":"N","osm_id":982102,"countrycode":"FR",
            "osm_key":"shop","osm_value":"convenience"},
         "geometry":{"coordinates":[5.0,45.070]}},
        {"properties":{"osm_type":"N","osm_id":982103,"countrycode":"FR",
            "osm_key":"shop","osm_value":"bakery"},
         "geometry":{"coordinates":[5.0,46.000]}}, # Too far; reject
    ]}
orig_http=planner._request_json
planner._request_json=multi_photon
try:
    water_batch=planner._photon_anchor_resource(
        {"lat":45.05,"lon":5.0},"water",
        ("amenity:drinking_water","natural:spring"),5.5)
    assert water_batch
    extra=water_batch.get("_photon_alternatives") or []
    assert len(extra)==3,extra
    assert len({r["source_url"] for r in [water_batch]+extra})==4
    assert {r["source_url"].split("/")[-1] for r in [water_batch]+extra}=={
        "982001","982002","982003","982004"}
    from backend.trekbrain_water_evidence_v9 import confirmed_water_reference
    non_potable=next(r for r in [water_batch]+extra if r["source_url"].endswith("/982003"))
    assert non_potable["water_status"]=="not_potable"
    assert not confirmed_water_reference(non_potable)
    assert confirmed_water_reference(water_batch)
    assert len(extra_http)==1

    extra_http.clear()
    batch=planner._postroute_corridor_resources(
        [{"lat":45.0,"lon":5.0},{"lat":45.05,"lon":5.0},
         {"lat":45.10,"lon":5.0}],
        {"water":True,"food":True,"_water_corridor_anchors":[
            {"lat":45.05,"lon":5.0,"route_day":1}]},[])
finally:
    planner._request_json=orig_http
assert len(extra_http)<=6,extra_http
assert len(extra_http)==3,extra_http # One water and two food queries
assert all("_photon_alternatives" not in x for x in batch)
water_ids={x["source_url"].split("/")[-1] for x in batch if x["category"]=="water"}
food_ids={x["source_url"].split("/")[-1] for x in batch if x["category"]=="food"}
assert water_ids=={"982001","982002","982003","982004"},water_ids
assert food_ids=={"982101","982102"},food_ids
before_route=[[45.0,5.0],[45.05,5.0],[45.1,5.0]]
multi_plan={"duration_days":2,
    "stages":[{"day":1,"distance_km":5.5},{"day":2,"distance_km":5.5}],
    "route_preview":{"coords":[r[:] for r in before_route]},
    "water":[],"resources":[]}
resources._merge_supplemented_resources(multi_plan,batch)
resources.enrich_resources(multi_plan)
coverage=resources._resource_coverage(multi_plan,{"water":True,"food":True})
assert coverage["days_with_water"]==[1,2],coverage
assert coverage["days_with_food"]==[1,2],coverage
assert multi_plan["route_preview"]["coords"]==before_route
assert any(x["status"]=="not_potable" for x in multi_plan["map_resources"]["evidence_points"]
           if x["kind"]=="water")
print("Photon multi evidence: two water days/two food days, explicit unsafe tap preserved, one-call harvest, immutable geometry: PASS")
