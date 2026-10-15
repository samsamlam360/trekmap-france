#!/usr/bin/env python3
"""Read-only discovery of existing OSM walking route relations in Centre-Val de Loire.

No guessed coordinates, no edits to production data. Candidate geometries must be
retrieved and validated separately before publication.
"""
import json, requests, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"centre_relation_candidates.json"
HEADERS={"User-Agent":"TrekMap-France hiking-source-audit/1.0 (ODbL attribution)"}
OVERPASS_ENDPOINTS=[
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]
# Bounding box deliberately broad; candidate acceptance later requires French regional geometry.
QUERY='[out:json][timeout:95];relation["route"~"^(hiking|foot)$"]["network"~"^(nwn|rwn|lwn)$"](46.15,-0.45,49.05,4.0);out tags center;'
TERMS=["Touraine","Sologne","GR 3","GR3","GR 41","GR 46","GR 35","GR 36","GR 655","Berry","Vallée du Cher","Compostelle","Loire","Brenne","Perche","Vendôme","Beauce"]

def main():
  diag={"overpass_errors":[],"search_errors":[]}
  relations={}
  for server in OVERPASS_ENDPOINTS:
    try:
      r=requests.post(server,data={"data":QUERY},headers=HEADERS,timeout=(15,115))
      r.raise_for_status()
      items=r.json().get("elements",[])
      diag["overpass_server"]=server
      diag["overpass_count"]=len(items)
      for x in items:
        tags=x.get("tags") or {}
        if not tags.get("name") and not tags.get("ref"):continue
        c=x.get("center") or {}
        if not (46.15<float(c.get("lat",-99))<49.05 and -0.45<float(c.get("lon",-99))<4.0):continue
        rel_id=int(x["id"])
        relations[rel_id]={"id":rel_id,"name":tags.get("name",""),"ref":tags.get("ref",""),
           "network":tags.get("network",""),"from":tags.get("from",""),"to":tags.get("to",""),
           "lat":c.get("lat"),"lon":c.get("lon"),"source":"overpass"}
      break
    except Exception as e:diag["overpass_errors"].append(str(e)[:220])
  # Search for explicitly named multi-day trails in case an Overpass provider is unavailable.
  api="https://hiking.waymarkedtrails.org/api/v1/list/search"
  searches={}
  for term in TERMS:
    try:
      r=requests.get(api,params={"query":term,"limit":60,"locale":"fr"},headers=HEADERS,timeout=(10,24))
      r.raise_for_status()
      candidates=r.json().get("results") or []
      matches=[]
      for x in candidates:
        name=str(x.get("name") or "")
        ref=str(x.get("ref") or "")
        if x.get("type")=="relation" and (name or ref):
          matches.append({"id":x.get("id"),"name":name,"ref":ref,"network":x.get("group"),"itinerary":x.get("itinerary")})
      searches[term]=matches[:60]
    except Exception as e:diag["search_errors"].append({"q":term,"error":str(e)[:170]})
  values=sorted(relations.values(),key=lambda x:(x["network"] not in ("nwn","rwn"),-len(x["name"]),x["id"]))
  payload={"source":"OpenStreetMap (ODbL 1.0), Waymarked Trails search","diagnostics":diag,
           "bbox":[-0.45,46.15,4.0,49.05],"overpass_routes":values,
           "waymarked_search":searches}
  OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  print("CENTRE OSM PROBE",len(values),"overpass relation names",len(searches),"search queries")
  for x in values[:50]:print(x["id"],x["name"][:65],x["ref"],x["network"],x["lat"],x["lon"])
if __name__=="__main__":main()
