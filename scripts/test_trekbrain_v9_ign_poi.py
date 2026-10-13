"""Network-free official IGN POI recovery for department-qualified landmarks.

No hard-coded benchmark destinations in production and no coordinate guesses.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import free_planner_v2 as geo
from backend import trekbrain_geo_fallback_v9 as ign

original = geo._request_json
calls = []
def feature(name, lon, lat, code, score):
    return {
        "type":"Feature", "geometry":{"type":"Point","coordinates":[lon,lat]},
        "properties":{
            "name":[name], "toponym":name,
            "depcode":[code], "city":["Unknown"], "score":score,
        }
    }

def mocked(url, **kw):
    calls.append((url, kw))
    if url == ign.DEPARTMENTS_URL:
        return [
            {"nom":"Haut-Rhin","code":"68"},
            {"nom":"Haute-Savoie","code":"74"},
            {"nom":"Jura","code":"39"},
        ]
    assert url == ign.IGN_GEOCODAGE_URL, url
    if kw["params"]["q"] == "Lac Blanc":
        return {"features":[
            feature("Lac Blanc", 7.090404, 48.126343, "68", .85),
            feature("Lac Blanc", 6.90, 45.98, "74", .99),
            feature("Lac Blanc", 7.09, 48.12, "68", .20),
            feature("Lac Bleu", 7.10, 48.10, "68", .99),
        ]}
    if kw["params"]["q"] == "Cascades du Hérisson":
        return {"features":[
            feature("Point Information des Cascades du Hérisson", 5.850216, 46.613293, "39", .67),
            feature("Maison des Cascades du Hérisson", 5.849918, 46.613383, "39", .65),
            feature("Point Information des Cascades du Hérisson", 5.850216, 46.613293, "68", .99),
        ]}
    return {"features":[]}

geo._request_json=mocked
try:
    lac=ign.geocode_ign_poi("Lac Blanc, Haut-Rhin, France")
    assert len(lac)==1 and lac[0]["department_code"]=="68", lac
    assert abs(lac[0]["lat"]-48.126343)<0.00001
    assert lac[0]["geocode_precision"]=="named-poi"
    assert lac[0]["geocode_provider"]=="ign-bdtopo-poi"
    assert len(calls)==2 and calls[0][0]==ign.DEPARTMENTS_URL
    assert calls[1][1]["params"]["index"]=="poi"
    assert calls[1][1]["params"]["depcode"]=="68"
    assert all(call[1]["retries"]==1 and call[1]["cache_empty"] is False for call in calls)

    calls.clear()
    cascades=ign.geocode_ign_poi("Cascades du Hérisson, Jura")
    assert len(cascades)==2 and all(x["department_code"]=="39" for x in cascades), cascades
    assert "Cascades du Hérisson" in cascades[0]["name"], cascades
    assert abs(cascades[0]["lon"]-5.850216)<0.002

    # Homonymous mountains without department are fundamentally ambiguous.
    calls.clear()
    assert ign.geocode_ign_poi("Lac Blanc") == []
    assert not calls, calls
    assert ign.geocode_ign_poi("Lac Blanc, France") == []
    assert ign.geocode_ign_poi("Lac Blanc, Haut-Rhin, Espagne") == []
    assert not calls, calls

    # The index may return correct spelling in the WRONG department.
    calls.clear()
    assert ign.geocode_ign_poi("Lac Blanc, Jura") == []
    assert all(url in {ign.DEPARTMENTS_URL,ign.IGN_GEOCODAGE_URL} for url,_ in calls)

    # Official department names must match in full, not fuzzy "Rhine" or
    # unrelated similarly named places.
    calls.clear()
    assert ign.geocode_ign_poi("Lac Blanc, Rhin") == []
    assert len(calls)==1 and calls[0][0]==ign.DEPARTMENTS_URL, calls

    # Department code works without requesting an official name lookup;
    # the provider output still has to carry the matching code.
    calls.clear()
    code=ign.geocode_ign_poi("Lac Blanc, 68")
    assert len(code)==1 and code[0]["department_code"]=="68"
    assert len(calls)==1 and calls[0][0]==ign.IGN_GEOCODAGE_URL
finally:
    geo._request_json=original

# Verify integration into production fast-geocoder on a fully failed OSM/IGN
# chain, without any real provider or user data.
from backend import smart_planner_v3 as v3
from backend import smart_planner_v5 as v5
from backend import smart_planner_v9 as v9
from backend import trekbrain_commune_fallback_v9 as communes
from backend import trekbrain_speed_v9 as speed

original_nom=geo._geocode_nominatim
original_photon=geo._geocode_photon
original_address=ign.geocode_ign
original_communes=communes.geocode_commune
original_poi=ign.geocode_ign_poi
original_local=geo._local_geocode
original_cooldown=speed._NOMINATIM_COOLDOWN_UNTIL
events=[]
geo._geocode_nominatim=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("Nominatim HTTP 429"))
geo._geocode_photon=lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError("Photon timeout"))
geo._local_geocode=lambda query: []
ign.geocode_ign=lambda query,**kwargs: (events.append("ign_address") or [])
communes.geocode_commune=lambda query,**kwargs: (events.append("commune") or [])
ign.geocode_ign_poi=lambda query,**kwargs: (
    events.append("poi") or
    [{"name":"Official natural POI", "lat":48.126343,"lon":7.090404,
      "department_code":"68","geocode_provider":"ign-bdtopo-poi"}]
)
try:
    speed._INSTALLED=False
    speed._NOMINATIM_COOLDOWN_UNTIL=0.0
    speed.install_fast_planning(v3,v5,v9)
    result=v3._geocode("Lac Blanc, Haut-Rhin, France")
    assert result and result[0]["geocode_provider"]=="ign-bdtopo-poi",result
    assert events==["ign_address","commune","poi"],events
finally:
    geo._geocode_nominatim=original_nom
    geo._geocode_photon=original_photon
    geo._local_geocode=original_local
    ign.geocode_ign=original_address
    communes.geocode_commune=original_communes
    ign.geocode_ign_poi=original_poi
    speed._NOMINATIM_COOLDOWN_UNTIL=original_cooldown

print("IGN named POI: precise department, homonym safety, official index, real fast-geo integration PASS")
