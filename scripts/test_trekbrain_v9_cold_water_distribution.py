"""Twenty provider-free first-visit route shapes, water safety and OSM outage.

This is a deterministic regression test, NOT 20 live destination benchmarks:
no ORS, Overpass or Neon calls are made. It protects rare/uneven GPX shapes
and unknown/unsafe potable-water evidence throughout France.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import trekbrain_water_discovery_v9 as water
from backend import free_planner_v2 as free

def haversine(a, b):
    return water._distance_km(a,b)

def profile(base_lat, base_lon, n_dense, n_sparse, travel_km):
    # Deliberately put thousands of route vertices into the first kilometre.
    # A vertex-index sampling would fail to search the next ~60 km.
    start=[base_lat,base_lon]
    first=[[round(base_lat+0.009*i/n_dense,7),base_lon]
           for i in range(n_dense+1)]
    last=[[round(base_lat+0.009+(travel_km/111.3)*i/n_sparse,7),base_lon]
          for i in range(1,n_sparse+1)]
    return first+last

shapes=[]
for index in range(20):
    lat=42.7+index*0.25
    lon=-4.7+(index%5)*2.4
    coords=profile(lat,lon,1000+index*21,2+(index%3),30+index*1.5)
    samples=water._sample_route(coords,2+(index%5))
    assert 6<=len(samples)<=16, (index,len(samples))
    assert samples[0]==coords[0] and samples[-1]==coords[-1],index
    total=sum(haversine(a,b) for a,b in zip(coords,coords[1:]))
    sample_distances=[sum(haversine(a,b) for a,b in zip(samples[:i+1],samples[1:i+2]))
                      for i in range(len(samples)-1)]
    assert total>=29,index
    halfway=sum(1 for p in samples if p[0]>=lat+0.009+(coords[-1][0]-lat-0.009)*.5)
    assert halfway>=2,(index,halfway)
    assert any(p[0]>lat+0.10 for p in samples),index
    assert all(-90<=p[0]<=90 and -180<=p[1]<=180 for p in samples),index
    shapes.append(len(samples))
# Sparse two-point traces must also be sampled by real walked distance.
sparse=water._sample_route([[45.0,5.0],[45.55,5.0]],3)
assert len(sparse)==9 and len(set(tuple(p) for p in sparse))==9,sparse
assert water._sample_route([[45.0,5.0]]*200,4)==[[45.0,5.0]]
assert water._sample_route([],3)==[]
assert not water._element_point({"lat":95.0,"lon":6.0})
assert not water._element_point({"lat":45.0,"lon":190.0})
print("20 synthetic unseen-route geometries: distance-balanced water sampling in one bounded query: PASS")

plan={
    "duration_days":3,
    "route_preview":{"coords":profile(45,5,1800,2,60),"fallback":False},
    "water":[],
}
calls=[]
actual=free._request_json
def fake_request(url, **kwargs):
    calls.append((url,kwargs))
    return {"elements":[
        {"type":"node","id":101,"lat":45.02,"lon":5,
         "tags":{"amenity":"drinking_water","drinking_water":"yes","name":"Robinet"}},
        {"type":"node","id":102,"lat":45.10,"lon":5,
         "tags":{"amenity":"drinking_water","drinking_water":"no","name":"Attention"}},
        {"type":"node","id":103,"lat":45.20,"lon":5,
         "tags":{"natural":"spring","name":"Source naturelle"}},
        {"type":"node","id":104,"lat":45.30,"lon":5,
         "tags":{"man_made":"water_tap","water:potable":"no"}},
        # A repeated OSM element with contradictory tags must not override
        # the explicit warning even if the first record looked potable.
        {"type":"node","id":101,"lat":45.02,"lon":5,
         "tags":{"amenity":"drinking_water","drinking_water":"no"}},
        {"type":"node","id":105,"lat":199.0,"lon":5,
         "tags":{"amenity":"drinking_water","drinking_water":"yes"}},
    ]}
free._request_json=fake_request
try:
    discovered=water.discover_water_points(None,plan)
finally:
    free._request_json=actual
assert len(calls)==1,calls
params=calls[0][1]
assert params["retries"]==1 and params["timeout"]<=1.6 and params["ttl"]==3600,params
query=params["data"]["data"]
assert query.count('["amenity"="drinking_water"]')<=16
assert query.count('["man_made"="water_tap"]')<=16
assert query.count('["natural"="spring"]')<=16
assert len(discovered)==4,discovered
by_id={row["source_url"].split("/")[-1]:row for row in discovered}
assert by_id["101"]["status"]=="not_potable",by_id
assert by_id["102"]["status"]=="not_potable",by_id
assert by_id["104"]["status"]=="not_potable",by_id
assert by_id["103"]["status"]=="unverified",by_id
assert "ne pas boire" in by_id["101"]["notes"]
assert "potabilité inconnue" in by_id["103"]["notes"]
assert all(p["display_only"] for p in discovered)
print("Contradictory OSM water, spring uncertainty and 1-query budget: PASS")

# Existing/cached positive water must be overruled by a new explicit negative
# from the same source. It must not be discarded by old coordinate-first dedup.
class Dummy:
    def enrich_resources(self,plan):
        plan.setdefault("map_resources",{})
        return plan
old_installed=water._INSTALLED
water._INSTALLED=False
dummy=Dummy()
try:
    water.install_water_discovery(None,dummy)
    existing={"name":"Fontaine","lat":45.02,"lon":5.0,
              "category":"water","source_url":"https://www.openstreetmap.org/node/101",
              "status":"potable_referenced","water_status":"potable_referenced"}
    result={"water":[existing],"duration_days":3,"route_preview":{"coords":[[45,5],[45.5,5]]}}
    saved=free._request_json
    free._request_json=fake_request
    try:
        merged=dummy.enrich_resources(result)
    finally:
        free._request_json=saved
    hit=next(x for x in merged["water"] if x["source_url"].endswith("/101"))
    assert hit["status"]=="not_potable",hit
    assert "ne pas boire" in hit["notes"]
    assert len(merged["water"])==4,merged["water"]
    preloaded={"water":[existing.copy()],"_terrain_osm_preloaded":True,"map_resources":{}}
    before=len(calls)
    dummy.enrich_resources(preloaded)
    assert len(calls)==before,"preloaded Overpass must not be called again"
finally:
    water._INSTALLED=old_installed

# Outage cannot fabricate water evidence or crash a valid route.
free._request_json=lambda *a,**k: (_ for _ in ()).throw(TimeoutError("Overpass"))
try:
    assert water.discover_water_points(None,plan)==[]
finally:
    free._request_json=actual

print("Cold-cache water merge, no duplicate lookup and provider-outage safety: PASS")


# Provider-free coverage of the new Overpass polyline query: six OSM filters
# are used regardless of how many path samples cover the missing days.
synthetic_samples=[[45+i*.025,5+(i%3)*.01] for i in range(16)]
compact_query=water._water_corridor_query(synthetic_samples)
assert compact_query.count("nwr(around:3200,")==6,compact_query
assert '["amenity"="drinking_water"]' in compact_query
assert '["amenity"="water_point"]' in compact_query
assert '["man_made"="water_well"]["drinking_water"="yes"]' in compact_query
assert '["man_made"="water_pump"]["drinking_water"="yes"]' in compact_query
assert f"{synthetic_samples[-1][0]:.6f},{synthetic_samples[-1][1]:.6f}" in compact_query
assert len(compact_query)<1300,len(compact_query)
assert water._water_corridor_query([])==""
# Source-identity conflicts: the new parse must retain access=private when
# another OSM result of the exact same source reports just amenity=drinking_water.
conflict_calls=[]
def private_source_request(url,**kwargs):
    conflict_calls.append(kwargs)
    return {"elements":[
        {"type":"node","id":110230,"lat":45.12,"lon":5.0,
         "tags":{"amenity":"drinking_water"}},
        {"type":"node","id":110230,"lat":45.12,"lon":5.0,
         "tags":{"amenity":"drinking_water","access":"private"}},
        {"type":"node","id":110231,"lat":45.21,"lon":5.0,
         "tags":{"amenity":"drinking_water","drinking_water":"no"}},
    ]}
from backend.trekbrain_water_evidence_v9 import confirmed_water_reference
saved_request=free._request_json
free._request_json=private_source_request
try:
    sources=water.discover_water_points(None,plan)
finally:
    free._request_json=saved_request
assert len(conflict_calls)==1,conflict_calls
assert conflict_calls[0]["data"]["data"].count("nwr(around:3200,")==6
source=next(row for row in sources if row["source_url"].endswith("/110230"))
assert source["osm_tags"].get("access")=="private",source
assert source["water_status"]=="potable_referenced",source
assert not confirmed_water_reference(source),source
assert "restreint" in source["notes"],source
unsafe=next(row for row in sources if row["source_url"].endswith("/110231"))
assert unsafe["water_status"]=="not_potable" and not confirmed_water_reference(unsafe)
print("Overpass one-line water corridor (6 filters / 1 request) and private-access preservation: PASS")
