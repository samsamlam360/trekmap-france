#!/usr/bin/env python3
"""Discover region-diverse, legally re-usable public hiking GeoJSON datasets.

Metadata survey only: downloads NO geometry, writes NO Neon data.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
import json, requests, re
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"national_trek_source_survey.json"
REGIONS=[
 "Bretagne","Normandie","Pays de la Loire","Centre-Val de Loire",
 "Nouvelle-Aquitaine","Bourgogne-Franche-Comté","Grand Est",
 "Hauts-de-France","Île-de-France","Auvergne-Rhône-Alpes","Corse",
 "Occitanie","Provence-Alpes-Côte d'Azur"
]
QUERIES=["itinéraires de randonnée","grande randonnée","sentiers randonnée","parc naturel"]
HEADERS={"User-Agent":"TrekMap-France-licence-check/1.0"}
def fetch(query):
    try:
        r=requests.get("https://www.data.gouv.fr/api/1/datasets/",
            params={"q":query,"page_size":70},timeout=28,headers=HEADERS)
        r.raise_for_status()
        return query,r.json().get("data",[]),""
    except Exception as ex:return query,[],repr(ex)
def allowed(license):
    if isinstance(license,dict):
        lic=" ".join(str(license.get(x,"")) for x in ("id","title"))
    else:lic=str(license)
    lic=lic.casefold()
    return any(x in lic for x in ("lov2","fr-lo","licence ouverte","open licence")) and "not specified" not in lic
def candidates(query,metadata):
    result=[]
    for item in metadata:
        if not allowed(item.get("license")):continue
        res=[]
        for r in item.get("resources",[]):
            fmt=str(r.get("format") or "").casefold()
            if fmt not in ("geojson","json","gpkg","zip"):continue
            size=r.get("filesize") or 0
            if size and (size>70_000_000 or size<300):continue
            id=r.get("id");url=r.get("url")
            if not id or not url:continue
            res.append({"id":id,"format":fmt,"size":size,"name":str(r.get("title") or "")[:90]})
        if not res:continue
        title=item.get("title") or ""
        sample=" ".join([title,item.get("description") or "",query]).casefold()
        if not any(x in sample for x in ("rando","itineraire","itinéraire","sentier","grande randonnée","gr ","pédestre")):continue
        score=sum(5 if x in title.casefold() else 1 for x in ("itinéraires","randon","grande rand","gr ","geotrek"))
        score+=10 if any(r["format"]=="geojson" for r in res) else 0
        score+=3 if any(r["size"]>100000 for r in res) else 0
        result.append({"id":item.get("id"),"slug":item.get("slug"),"title":title,
        "producer":str((item.get("organization") or {}).get("name") or "")[:75],
        "license":item.get("license"),"score":score,
        "resource":sorted(res,key=lambda x:(x["format"]!="geojson",-x["size"]))[:3]})
    return result
def main():
    terms=list(dict.fromkeys(["randonnée","randonnee","randonnées","randonnees",
         "itinéraires de randonnée","sentiers de randonnée","itinéraires",
         "geotrek","randonnées du","grande randonnée","GR","randonnée pédestre",
         "itinéraires de randonnées","randos"]))
    combined={}
    diagnostics={}
    with ThreadPoolExecutor(max_workers=6) as exe:
        futures=[exe.submit(fetch,t) for t in terms]
        for future in as_completed(futures):
            term,rows,err=future.result()
            vals=candidates(term,rows)
            diagnostics[term]={"total":len(rows),"eligible":len(vals),"error":err}
            for x in vals:
                key=x["id"]
                if not key:continue
                if key not in combined or combined[key]["score"]<x["score"]:
                    combined[key]=x
            print(term,diagnostics[term],flush=True)
    data=sorted(combined.values(),key=lambda x:(-x["score"],x["title"]))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"queries":diagnostics,"datasets":data},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("TOTAL DISCOVERED",len(data))
if __name__=="__main__":main()
