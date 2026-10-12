"""Offline distance-constraint regression: Huelgoat-sized stages and safety.

The real route geometry, length, stays, night availability and quality score
remain untouched. No geocoder, routing, Overpass, Neon or API credentials.
"""
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.trekbrain_distance_contract_v9 import annotate_daily_distance


def plan(distances):
    return {
        "route_preview":{"coords":[[48.36,-3.75],[48.42,-3.81],[48.36,-3.75]],
                         "distance_km":sum(distances),"fallback":False},
        "duration_days":len(distances),
        "stages":[{"day":i+1,"distance_km":d,
                   "overnight":"Nuitée à confirmer" if i<len(distances)-1 else "Fin du trek",
                   "safety_notes":"Prévoir de l'eau."}
                  for i,d in enumerate(distances)],
        "planner":{"strategy":"ors-round-trip"},
        "logistics":{"nights_required":max(0,len(distances)-1),"status":"partial"},
        "confidence":{"score":78,"limitations":["Conditions météo non vérifiées."]},
        "advisor_notes":["Le tracé est calculé."],
        "trekbrain":{"quality":{"score":59,"blockers":["étapes mal équilibrées"]}},
    }

intent={"days":2,"daily_target":16.0,"daily_max":20.0}
huelgoat=plan([20.6,20.6])
original_geometry=deepcopy(huelgoat["route_preview"])
original_logistics=deepcopy(huelgoat["logistics"])
original_quality=deepcopy(huelgoat["trekbrain"])
annotate_daily_distance(huelgoat,intent)
details=huelgoat["planner"]["distance_contract"]
assert details["target_exceeded"] is True
assert details["actual_average_km"]==20.6
assert details["daily_target_km"]==16.0
assert details["longest_day_km"]==20.6
assert details["days_exceeding"]==[
    {"day":1,"distance_km":20.6,"extra_pct":29,"exceeds_limit":True},
    {"day":2,"distance_km":20.6,"extra_pct":29,"exceeds_limit":True},
],details
assert all("20.6 km" in x["safety_notes"] and "16.0 km" in x["safety_notes"]
           for x in huelgoat["stages"])
assert all("Prévoir de l'eau." in x["safety_notes"] for x in huelgoat["stages"])
assert huelgoat["route_preview"]==original_geometry
assert huelgoat["logistics"]==original_logistics
assert huelgoat["trekbrain"]==original_quality
assert huelgoat["confidence"]["score"]==78
assert "Distance demandée dépassée" in huelgoat["confidence"]["limitations"][-1]
snapshot=deepcopy(huelgoat)
annotate_daily_distance(huelgoat,intent)
assert huelgoat==snapshot,"Repeated pipeline must not duplicate warnings"

# Saint-Antonin: 20.2 km each day still exceeds the 16 km requested.
saint=plan([20.2,20.2])
annotate_daily_distance(saint,{**intent,"daily_max":21.0})
assert saint["planner"]["distance_contract"]["target_exceeded"]
assert not saint["planner"]["distance_contract"]["days_exceeding"][0]["exceeds_limit"]
# Modest variations are normal and must not generate an alarming warning.
for kms in [[16,16],[17.6,17.6],[14.2,14.2],[18.2,18.3]]:
    good=plan(kms)
    orig_stages=deepcopy(good["stages"])
    annotate_daily_distance(good,intent)
    assert not good["planner"]["distance_contract"]["target_exceeded"],good
    assert good["stages"]==orig_stages,good
    assert len(good["confidence"]["limitations"])==1,good

# Thresholds distinguish genuine excess from rounding uncertainties.
border=plan([20.12,18.0])
annotate_daily_distance(border,intent)
assert border["planner"]["distance_contract"]["target_exceeded"]
assert border["planner"]["distance_contract"]["days_exceeding"][0]["exceeds_limit"] is False

# A valid maximum below the ordinary +18% trigger must still be honoured.
narrow=plan([18.2,17.8])
annotate_daily_distance(narrow,{"days":2,"daily_target":16,"daily_max":18})
assert narrow["planner"]["distance_contract"]["target_exceeded"]

for malformed,config in [
    ({"stages":[{"distance_km":20.6}]},{"days":2,"daily_target":16}),
    ({"stages":[{"distance_km":"NaN"}]},{"days":1,"daily_target":16}),
    ({"stages":[{"distance_km":20.6}]},{"days":1,"daily_target":0}),
    ({"stages":None},{"days":1,"daily_target":16}),
]:
    before=deepcopy(malformed)
    assert annotate_daily_distance(malformed,config)==before

long=plan([13.0,27.0,14.0])
annotate_daily_distance(long,{"days":3,"daily_target":18.0,"daily_max":24.0})
assert [r["day"] for r in long["planner"]["distance_contract"]["days_exceeding"]]==[2]
assert "au lieu d'environ 18.0 km" in long["stages"][1]["safety_notes"]
assert long["stages"][0]["safety_notes"]=="Prévoir de l'eau."

print("TrekBrain daily distance: 2/2 excessive days surfaced, honest route and nights preserved, safe variants PASS")
