#!/usr/bin/env python3
"""Audit official government hiking datasets across currently missing regions.

Filters real connected walking geometries, without adding anything to Neon.
"""
import json,sys,requests,concurrent.futures
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_long_treks as longs
import prepare_open_treks as helper
REPORT=ROOT/"data"/"national_long_trek_candidates.json"
TARGETS={
"itineraires-de-randonnee-circuits-qualite-departement-du-calvados":"Normandie",
"itineraires-randonnee-pedestre-pdesi-cd76-20210510-1":"Normandie",
"boucles-de-randonnee-inscrites-au-plan-departemental-des-itineraires-de-petite-randonnee-du-departement-de-la-dordogne":"Nouvelle-Aquitaine",
"departement-de-la-nievre-randonnees":"Bourgogne-Franche-Comté",
"traces-des-circuits-randonnees-pedestres-tours-metropole-1":"Centre-Val de Loire",
"circuits-de-randonnee-pedestre-en-eure-et-loir":"Centre-Val de Loire",
"circuits-de-randonnees-sur-le-territoire-de-saint-nazaire-agglo-1":"Pays de la Loire",
"circuits-de-randonnees-pour-le-territoire-de-cap-atlantique":"Pays de la Loire",
"les-circuits-de-randonnees-pedestres-sur-le-territoire-de-m2a":"Grand Est",
"plan-departemental-des-itineraires-de-promenades-et-de-randonnees-du-departement-du-pas-de-calais":"Hauts-de-France",
"itineraires-de-randonnee-pedestre-de-lannion-tregor-communaute":"Bretagne",
"parcs-naturels-regionaux-itineraires-de-randonnees-a-pied-a-velo-a-vtt-et-a-cheval-publie-dans-chemins-des-parcs":"Provence-Alpes-Côte d'Azur",
"circuits-de-randonnees-3":"Normandie",
"itineraires-de-randonnee-inscrits-au-plan-departemental-des-itineraires-de-promenade-et-de-randonnee-pdipr-du-gers-1":"Occitanie",
"les-circuits-inscrits-au-plan-departemental-des-itineraires-de-promenade-et-de-randonnee-puy-de-dome-spatial-ville-de-clermont-ferrand":"Auvergne-Rhône-Alpes"
}
HEADERS={"User-Agent":"TrekMap-France-dataset-audit/1.0"}
def allowed(obj):
    lic=obj.get("license")
    if isinstance(lic,dict):lic=" ".join(str(lic.get(x,"")) for x in ("id","title"))
    return any(x in str(lic).casefold() for x in ("lov2","fr-lo","licence ouverte","open licence"))
def read(slug,region):
    result={"slug":slug,"region":region,"resources":[],"candidates":[]}
    try:
        meta=requests.get("https://www.data.gouv.fr/api/1/datasets/"+slug+"/",
                          headers=HEADERS,timeout=(15,25))
        meta.raise_for_status();meta=meta.json()
        if not allowed(meta):
            result["error"]="Not under Licence Ouverte"
            return result
        result["producer"]=(meta.get("organization") or {}).get("name") or "Producteur public"
        ids=[]
        for r in meta.get("resources",[]):
            fmt=str(r.get("format") or "").lower()
            if fmt not in ("geojson","json"):continue
            size=r.get("filesize") or 0
            if size and size>40_000_000:continue
            id=r.get("id")
            if id:ids.append((id,fmt,str(r.get("title") or ""),size))
        ids.sort(key=lambda v:(v[1]!="geojson",-v[3]))
        result["format_options"]=len(ids)
        for rid,fmt,title,size in ids[:2]:
            stats={"id":rid,"format":fmt,"size":size,"title":title[:90]}
            result["resources"].append(stats)
            try:
                raw=requests.get("https://www.data.gouv.fr/api/1/datasets/r/"+rid,
                                 headers=HEADERS,timeout=(15,75))
                raw.raise_for_status()
                if len(raw.content)>42_000_000:raise ValueError("Resource >42 MB")
                payload=raw.json()
                features=payload.get("features") if isinstance(payload,dict) else None
                if not isinstance(features,list):
                    raise ValueError("No GeoJSON FeatureCollection: "+str(list(payload)[:6]))
                stats["raw"]=len(features)
                stats["samples"]=[]
                accepted=[]
                for feature in features:
                    feat=longs.wgs84_feature(feature)
                    geometry=feat.get("geometry") or {}
                    if len(stats["samples"])<2:
                        stats["samples"].append({"keys":list((feat.get("properties") or {}).keys())[:15],
                           "geometry":geometry.get("type"),
                           "named":helper.attrs(feat.get("properties") or {},"nom","name","titre")})
                    src={"id":"regional-"+slug[:20],"producer":result["producer"],
                         "region":region,"dataset":"https://www.data.gouv.fr/datasets/"+slug}
                    # The user wants 1+ day hiking; >=23km, avoid minute local walks.
                    old_min=longs.MIN_KM
                    longs.MIN_KM=23.0
                    t=longs.make_route(feat,src,rid)
                    longs.MIN_KM=old_min
                    if t:
                        t["duration_days"]=max(1,int(round(t["distance"]/20)))
                        accepted.append(t)
                stats["accepted"]=len(accepted)
                result["candidates"]+=accepted
            except Exception as ex:
                stats["error"]=repr(ex)[:180]
        result["candidates"]=sorted(result["candidates"],key=lambda x:-x["distance"])[:25]
        result["accepted"]=len(result["candidates"])
    except Exception as ex:result["error"]=repr(ex)[:200]
    print(slug,"valid",len(result["candidates"]),[(r.get("raw"),r.get("accepted"),r.get("error")) for r in result["resources"]],flush=True)
    return result
def main():
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks=[pool.submit(read,s,r) for s,r in TARGETS.items()]
        for fut in concurrent.futures.as_completed(tasks):rows.append(fut.result())
    candidates=[c for row in rows for c in row["candidates"]]
    region_counts=Counter(c["region"] for c in candidates)
    data={"sources":rows,"routes":candidates,"by_region":region_counts,
          "count":len(candidates)}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print("REGIONS",dict(region_counts),"TOTAL",len(candidates))
if __name__=="__main__":main()
