#!/usr/bin/env python3
"""Stage genuine connected OSM hiking route relations in neglected regions.

The ODbL file stays independently accessible as a share-alike database.
No edits to Neon; only audit and attributable read-only GPS geometries.
"""
from pathlib import Path
import concurrent.futures,sys,requests,json,math
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_open_treks as gps
import prepare_long_treks as longer
OUT=ROOT/"data"/"osm_regional_treks_odbl.json"
API="https://hiking.waymarkedtrails.org/api/v1"
SOURCES=[
  ("Bretagne","GR37 Cœur de Bretagne",8373372,[-5.6,47.0,-0.6,49.1]),
  ("Bretagne","Tour des Marches de Bretagne",11093598,[-3.6,46.9,0.4,49.2]),
  ("Bourgogne-Franche-Comté","Le Tour du Morvan",12662183,[2.4,46.3,5.5,48.6]),
  ("Grand Est","Traversée du Massif des Vosges",20619685,[6.0,47.2,8.7,49.8]),
  ("Hauts-de-France","GR120 Sentier du Littoral",2139379,[1.1,49.4,4.5,51.25]),
  ("Île-de-France","Ceinture verte d'Île-de-France",2741382,[1.2,47.9,4.0,49.25]),
  ("Corse","Mare è Monti Nord",13731390,[8.1,41.3,10.0,43.2]),
  ("Corse","Mare è Monti Sud",10034463,[8.1,41.3,10.0,43.2]),
  ("Corse","Mare è Monti Livantinu",12440558,[8.1,41.3,10.0,43.2]),
]
HEADERS={"User-Agent":"TrekMap-France/ODbL-hiking-relation-research (attribution and sharealike)"}
def harvest(region,title,rid,bbox):
    result={"region":region,"name":title,"relation":rid}
    try:
        details=requests.get(f"{API}/details/relation/{rid}",timeout=(12,40),headers=HEADERS)
        details.raise_for_status()
        detail=details.json()
        result["detail"]={k:detail.get(k) for k in ("name","ref","official_length","group","bbox","linear")}
        response=requests.get(f"{API}/list/segments",params={"bbox":",".join(str(x) for x in bbox),
                                  "relations":str(rid)},headers=HEADERS,timeout=(12,60))
        response.raise_for_status()
        payload=response.json()
        if payload.get("type")!="FeatureCollection":raise ValueError("Unexpected segment response")
        features=payload.get("features") or []
        result["features"]=len(features)
        if not features:return result
        raw=[]
        for item in features:
            for line in gps.segments(item.get("geometry") or {}):
                points=gps.parse_line(line)
                if len(points)>=3:raw.append(points)
        result["segments"]=len(raw)
        result["segment_km"]=[round(gps.distance(p),1) for p in raw[:18]]
        if not raw:return result
        converted={"type":"MultiLineString","coordinates":[[[x[1],x[0]] for x in line] for line in raw]}
        rebuilt=longer.stitch(converted)
        if rebuilt is None:
            result["status"]="fragmented (rejected: no fictitious joins)"
            return result
        points,km=rebuilt
        if not 23<=km<=650:
            result["status"]="too short or huge";result["distance_km"]=round(km,1);return result
        compact=gps.simplify(points,max_points=1100)
        if len(compact)<3 or abs(gps.distance(compact)-km)/km>0.05:
            result["status"]="lossy simplification";return result
        source=f"https://www.openstreetmap.org/relation/{rid}"
        key=f"osm-rel:{rid}"
        label=(str(detail.get("name") or title)).strip()
        # Only label verified geospatial sections. Metadata may describe a
        # larger OSM superroute than the displayed clipped geometry.
        if detail.get("official_length") and km<0.75*float(detail["official_length"])/1000:
            label+=" · tronçon vérifié"
        description=(f"Randonnée pédestre cartographiée dans OpenStreetMap, relation {rid}. "
            f"Distance calculée du tracé réellement représenté : {km:.1f} km. "
            f"Durée indicative : environ {max(1,round(km/20))} jours. "
            f"Dénivelé non renseigné (0 ne signifie pas terrain plat). "
            f"Vérifier le balisage, la praticabilité, les restrictions et les hébergements avant départ. "
            f"Source : {source} ; © les contributeurs OpenStreetMap, ODbL 1.0, "
            f"attribution et partage à l'identique : https://www.openstreetmap.org/copyright. "
            f"Référence : {key}.")
        result["status"]="accepted";result["distance_km"]=round(km,2)
        result["route"]={"source_key":key,"source_name":"Contributeurs OpenStreetMap / Waymarked Trails",
          "source_url":source,"license":"Open Data Commons ODbL 1.0",
          "name":label[:155],"region":region,"distance":round(km,2),
          "difficulty":"medium","elevation":0,
          "duration_days":max(1,round(km/20)),
          "description":description,
          "route_type":"Boucle" if gps.haversine(points[0],points[-1])<0.35 else "Traversée",
          "geometry":{"type":"LineString","coordinates":[[v[1],v[0]] for v in compact]}}
        return result
    except Exception as e:
        result["error"]=str(e)[:230]
        return result
def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        tasks=[pool.submit(harvest,*row) for row in SOURCES]
        rows=[task.result() for task in concurrent.futures.as_completed(tasks)]
    routes=[r["route"] for r in rows if r.get("status")=="accepted"]
    for r in rows:r.pop("route",None)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"license":"Open Data Commons ODbL 1.0",
        "attribution":"© les contributeurs OpenStreetMap, ODbL 1.0",
        "source":"https://hiking.waymarkedtrails.org/",
        "diagnostics":rows,"routes":routes},ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print("OSM routes accepted",len(routes))
    for r in rows:print(r["region"],r["name"],r.get("status"),r.get("distance_km"),r.get("error",""),flush=True)
if __name__=="__main__":main()
