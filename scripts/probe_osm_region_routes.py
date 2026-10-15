#!/usr/bin/env python3
"""Probe OpenStreetMap relation routes in currently missing metropolitan regions.

Staging only. Use OpenStreetMap ODbL attribution and share-alike separately.
"""
import json,requests,urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"osm_region_route_probe.json"
API="https://hiking.waymarkedtrails.org/api/v1/"
ROUTES={
 "Bretagne":(["GR34","Tour de Bretagne"],[-5.2,47.2,-1.0,48.9]),
 "Bourgogne-Franche-Comté":(["GR13","Tour du Morvan","GR de Pays Tour du Morvan"],[2.65,46.5,5.5,48.4]),
 "Grand Est":(["GR5","Traversée des Vosges","GR53"],[6.3,47.4,8.6,49.6]),
 "Hauts-de-France":(["GR120","Sentier du Littoral"],[1.4,49.8,4.3,51.2]),
 "Île-de-France":(["GR1","GR11","Ceinture Verte de l'Île-de-France"],[1.4,48.0,3.7,49.2]),
 "Normandie":(["GR223","Tour du Cotentin"],[-2.1,48.4,1.8,50.1]),
 "Pays de la Loire":(["GR3","GR34"],[-2.8,46.7,0.0,48.8]),
 "Corse":(["GR20","Mare e Monti"],[8.45,41.3,9.7,43.1])
}
HEADERS={"User-Agent":"TrekMap-France-ODbL-hiking-research/1.0"}
def request(region,term):
    result={"region":region,"query":term,"results":[]}
    try:
        r=requests.get(API+"list/search",params={"query":term,"limit":35,"locale":"fr"},
                       headers=HEADERS,timeout=28)
        r.raise_for_status()
        data=r.json()
        result["keys"]=list(data.keys())[:8]
        result["results"]=data.get("results",[])[:20]
    except Exception as ex:result["error"]=repr(ex)[:250]
    return result
def main():
    calls=[(r,t) for r,(terms,bb) in ROUTES.items() for t in terms]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(request,r,t) for r,t in calls]
        out=[f.result() for f in as_completed(futures)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"results":out},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for x in out:print(x["region"],x["query"],len(x["results"]),x.get("error",""),flush=True)
if __name__=="__main__":main()
