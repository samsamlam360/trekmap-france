#!/usr/bin/env python3
"""Discover source-attributed multi-day walking trails with real, connected geometries.

Read-only against the public government open-data catalogue. No DB writes.
Routes on disconnected sections, missing legal permission or fake joins are rejected.
"""
import json
import sys
from collections import Counter
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_open_treks as base

OUT=ROOT/"data"/"long_trek_candidates.json"
DIAG=ROOT/"data"/"long_trek_diagnostics.json"
MIN_KM=45.0
MAX_KM=280.0
DATASETS=[
    ("via-garona","via-garona-chemin-de-grande-randonnee-gr861",
     "Conseil départemental de Haute-Garonne","Occitanie",2),
    ("gard-gr","plan-departemental-des-itineraires-de-promenades-et-de-randonnees-pdipr-chemin-de-grande-randonnee",
     "Département du Gard","Occitanie",3),
    ("gard-grp","pdipr-chemin-de-grande-randonnee-de-pays-grp",
     "Département du Gard","Occitanie",3),
    ("cevennes-long","itineraires-de-randonnee-du-parc-national-des-cevennes",
     "Parc national des Cévennes","Occitanie",1),
    ("ecrins-long","randonnees-du-parc-national-des-ecrins",
     "Parc national des Écrins","Provence-Alpes-Côte d'Azur",1),
    ("vercors-trails","itineraires-de-randonnee-sur-le-parc-du-vercors",
     "Parc naturel régional du Vercors","Auvergne-Rhône-Alpes",1),
]
# Resource IDs already validated for the 140-trail public batch.
KNOWN={
    "cevennes-long":["4eee2f30-32de-4900-9591-be5ee3003e4d"],
    "ecrins-long":["0c62905f-a580-4cee-afc1-5feb9607160d"]
}
HEADERS={"User-Agent":"TrekMap-France/long-distance-open-data-review (attributed educational use)",
         "Accept":"application/json, application/geo+json;q=0.9,*/*;q=0.5"}

def select_resources(metadata,source_id,maximum):
    items=[]
    for resource in metadata.get("resources") or []:
        fmt=str(resource.get("format") or "").lower().strip(".")
        if fmt not in ("geojson","json"):continue
        if resource.get("filesize",0) and int(resource["filesize"])>70_000_000:continue
        if resource.get("type") in ("documentation","other"):continue
        item_id=str(resource.get("id") or "").strip()
        if not item_id:continue
        score=(0 if fmt=="geojson" else 1,
               0 if "geojson" in str(resource.get("title") or "").lower() else 1,
               str(resource.get("title") or ""))
        items.append((score,item_id,fmt))
    items.sort(key=lambda x:x[0])
    explicit=KNOWN.get(source_id,[])
    selected=list(explicit)
    # An independently published GeoJSON file often differs from the JSON API
    # export and may contain the complete lines.
    for _,id,fmt in items:
        if id not in selected:selected.append(id)
    return selected[:maximum],len(items)

def fetch_resource(rid):
    url="https://www.data.gouv.fr/api/1/datasets/r/"+rid
    r=requests.get(url,headers=HEADERS,timeout=(14,85))
    r.raise_for_status()
    if len(r.content)>72_000_000:raise ValueError("resource too large")
    try:content=r.json()
    except ValueError as err:raise ValueError("resource not JSON GeoJSON") from err
    if not isinstance(content,dict):raise ValueError("resource JSON is not an object")
    if content.get("type")=="FeatureCollection" and isinstance(content.get("features"),list):
        return content["features"],r.url
    if content.get("type")=="Feature" and isinstance(content.get("geometry"),dict):
        return [content],r.url
    raise ValueError("unexpected schema "+str(list(content)[:7]))

def stitch(geometry):
    raw=[base.parse_line(v) for v in base.segments(geometry)]
    lines=[v for v in raw if len(v)>=3]
    if not lines:return None
    if len(lines)==1:points=lines[0]
    else:
        # Only join actual consecutive endpoints, with max 20m tolerance.
        ls=[list(v) for v in lines]
        anchor=max(range(len(ls)),key=lambda i:base.distance(ls[i]))
        points=ls.pop(anchor)
        while ls:
            best=None
            for i,line in enumerate(ls):
                for dist,kind,reverse in (
                    (base.haversine(points[-1],line[0]),"append",False),
                    (base.haversine(points[-1],line[-1]),"append",True),
                    (base.haversine(points[0],line[-1]),"prepend",False),
                    (base.haversine(points[0],line[0]),"prepend",True),
                ):
                    if best is None or dist<best[0]:best=(dist,i,kind,reverse)
            if best is None or best[0]>0.02:return None
            gap,i,kind,reverse=best
            line=ls.pop(i)
            if reverse:line.reverse()
            if kind=="append":points+=line[1:] if gap<0.001 else line
            else:points=(line[:-1] if gap<0.001 else line)+points
    jumps=[base.haversine(a,b) for a,b in zip(points,points[1:])]
    if not jumps or max(jumps)>1.2:return None
    km=sum(jumps)
    if km<MIN_KM or km>MAX_KM:return None
    return points,km

def make_route(feature,src,rid):
    if not isinstance(feature,dict):return None
    p=feature.get("properties") or {}
    if not isinstance(p,dict) or not base.is_walk(p):return None
    rawname=base.attrs(p,"nom","name","nom_iti","nom_itineraire","libelle","nom_du_circuit",
                       "intitule","titre","parcours","nom_gr","nom_gr_pays","codegr",
                       "nom de l itineraire","nomgr","itineraire","nom du gr")
    if not rawname:
        rawname=next((v for k,v in p.items() if ("nom" in base.folded(k) or
            base.folded(k).startswith("label")) and isinstance(v,str) and v.strip()),None)
    if not rawname:return None
    name=" ".join(str(rawname).split())[:155]
    if len(name)<4 or name.isdigit():return None
    normname=base.folded(name)
    if any(word in normname for word in ("gravel","vtt","velo","cyclo","bike","trail running","en trail")):
        return None
    extracted=stitch(feature.get("geometry") or {})
    if not extracted:return None
    full,km=extracted
    simple=base.simplify(full,max_points=900)
    if len(simple)<3 or abs(base.distance(simple)-km)/km>0.05:return None
    source={ "id":src["id"],"producer":src["producer"],
        "region":src["region"],"dataset":src["dataset"] }
    # Build source key and name with consistent attribution using existing helper.
    feature_copy={"type":"Feature","geometry":{"type":"LineString",
        "coordinates":[[p[1],p[0]] for p in simple]},"properties":p}
    # Existing normalizer caps distance at 90 km: keep long geometry here.
    import hashlib
    sig=hashlib.sha256(json.dumps([src["id"],rid,str(feature.get("id") or ""),
          name,full[0],full[-1]],ensure_ascii=False).encode()).hexdigest()[:18]
    key=src["id"]+":"+sig
    elev=base.attrs(p,"denivele_positif","denivele positif","denivele","d_plus","elevation_gain")
    try:
        elevation=round(float(str(elev).replace(",","."))) if elev is not None else 0
        if not 0<=elevation<=40000:elevation=0
    except (TypeError,ValueError):elevation=0
    diff=base.folded(base.attrs(p,"difficulte","difficulté","difficulty") or "")
    difficulty="medium"
    if "facile" in diff or "easy" in diff:difficulty="easy"
    if "difficile" in diff or "hard" in diff:difficulty="hard"
    if "tres difficile" in diff or "extreme" in diff:difficulty="extreme"
    if any(x in diff for x in ("moyen","medium")):difficulty="medium"
    loop=base.haversine(full[0],full[-1])<0.30
    days=max(2,round(km/19))
    desc=(f"Itinéraire de randonnée longue distance publié par {src['producer']}. "
          f"Longueur géographique estimée : {km:.1f} km. "
          f"Durée indicative : environ {days} jours, non garantie et sans découpage officiel vérifié. "
          f"{'Dénivelé non renseigné (0 ne signifie pas terrain plat). ' if not elevation else ''}"
          f"{'Difficulté non vérifiée par la source. ' if not diff else ''}"
          f"Tracé officiel à recontrôler avant départ : balisage, accès, météo et hébergements. "
          f"Source : {src['dataset']} ; licence : Licence Ouverte / Open Licence version 2.0. "
          f"Référence : {key}.")
    return {"source_key":key,"source_name":src["producer"],"source_url":src["dataset"],
            "source_resource_id":rid,
            "license":"Licence Ouverte / Open Licence version 2.0",
            "name":name,"region":src["region"],"difficulty":difficulty,
            "distance":round(km,2),"elevation":elevation,"duration_days":days,
            "description":desc,"route_type":"Boucle" if loop else "Traversée",
            "geometry":{"type":"LineString","coordinates":[[p[1],p[0]] for p in simple]}}

def build():
    diagnostics={}
    found=[]
    for source_id,slug,producer,region,limit in DATASETS:
        d={"slug":slug,"status":"pending","resources":[]}
        diagnostics[source_id]=d
        try:
            url="https://www.data.gouv.fr/api/1/datasets/"+slug+"/"
            meta=requests.get(url,timeout=(12,30),headers=HEADERS)
            meta.raise_for_status()
            meta=meta.json()
            lic=meta.get("license") or ""
            d["license"]=lic
            # Reject records without explicit government Open Licence.
            if not any(x in str(lic).lower() for x in ("fr-lo","lov2","licence ouverte","open licence")):
                raise ValueError("License is not Open Licence: "+str(lic))
            src={"id":source_id,"producer":producer,"region":region,
                 "dataset":"https://www.data.gouv.fr/datasets/"+slug}
            resource_ids,count=select_resources(meta,source_id,limit)
            d["metadata_resources"]=count
            for rid in resource_ids:
                record={"id":rid,"accepted":0}
                d["resources"].append(record)
                try:
                    features,upstream=fetch_resource(rid)
                    record["raw_count"]=len(features)
                    record["schema"]=(
                      list((features[0].get("properties") or {}).keys())[:17]
                      if features else [])
                    if source_id in ("via-garona","gard-gr","gard-grp"):
                        record["samples"]=[]
                        for f in features[:8]:
                            segments=base.segments(f.get("geometry") or {})
                            lines=[base.parse_line(l) for l in segments]
                            record["samples"].append({
                                "name":base.attrs(f.get("properties") or {},"name","nom","nom_itineraire"),
                                "geometry_type":(f.get("geometry") or {}).get("type"),
                                "segments":len(lines),
                                "lengths_km":[round(base.distance(v),2) for v in lines[:12]],
                                "connected":stitch(f.get("geometry") or {}) is not None,
                                "is_walk":base.is_walk(f.get("properties") or {}),
                                "raw_coord_sample":(segments[0][:2] if segments else []),
                                "parsed_lines":sum(len(v)>=3 for v in lines),
                                "total_parsed_km":round(sum(base.distance(v) for v in lines),2),
                                "nearest_endpoint_km":[round(min((
                                    base.haversine(x,y)
                                    for j,other in enumerate(lines) if j!=i and len(other)>=3
                                    for x in (v[0],v[-1]) for y in (other[0],other[-1])),
                                    default=999),3) for i,v in enumerate(lines[:24]) if len(v)>=3],
                            })
                    candidates=[]
                    for f in features:
                        t=make_route(f,src,rid)
                        if t:candidates.append(t)
                    record["accepted"]=len(candidates)
                    record["preview"]=[{"name":x["name"],"km":x["distance"]}
                                        for x in sorted(candidates,key=lambda x:-x["distance"])[:12]]
                    found.extend(candidates)
                except Exception as e:
                    record["error"]=str(e)[:170]
            d["status"]="ok"
        except Exception as e:
            d["status"]="error";d["error"]=str(e)[:220]
        print(source_id, json.dumps(d,ensure_ascii=False)[:1800],flush=True)
    unique={}
    for r in found:
        # Same route appears in different representations/resources: collapse
        # only when source+name and geodesic endpoints match within 1km.
        folded=base.folded(r["name"])
        endpoints=r["geometry"]["coordinates"]
        aa=endpoints[0];bb=endpoints[-1]
        center=(round((aa[0]+bb[0])/2,2),round((aa[1]+bb[1])/2,2))
        identity=(r["source_name"],folded,center)
        prev=unique.get(identity)
        if prev is None or len(r["geometry"]["coordinates"])>len(prev["geometry"]["coordinates"]):
            unique[identity]=r
    routes=sorted(unique.values(),key=lambda x:(x["region"],x["name"],x["source_key"]))
    payload={"version":1,"distance_min_km":MIN_KM,"distance_max_km":MAX_KM,
             "routes":routes,"count":len(routes),"diagnostics":diagnostics}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    DIAG.write_text(json.dumps(diagnostics,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("FINAL candidate long treks:",len(routes), ">=80 km:",
          sum(r["distance"]>=80 for r in routes),"sources:",
          dict(Counter(x["source_name"] for x in routes)),flush=True)

if __name__=="__main__":
    build()
