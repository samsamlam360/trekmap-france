#!/usr/bin/env python3
"""Build a reviewable, offline catalog from four explicitly open-licensed French datasets.

The generator NEVER writes to Neon or republishes original copyrighted prose.
HTTP is used only in a manually reviewable GitHub Action; Render never fetches.
Every published trek includes the public producer, source URL, license and id.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "catalogue_open_treks.json"
SOURCES = [
    {
        "id": "lannion-tregor",
        "producer": "Lannion-Trégor Communauté",
        "region": "Bretagne",
        "dataset": "https://www.data.gouv.fr/datasets/itineraires-de-randonnee-pedestre-de-lannion-tregor-communaute",
        "download": "https://www.data.gouv.fr/api/1/datasets/r/225acbbe-22db-4d94-b213-0c0dd8c44584",
        "max_routes": 35,
    },
    {
        "id": "metropole-lyon",
        "producer": "Métropole de Lyon",
        "region": "Auvergne-Rhône-Alpes",
        "dataset": "https://www.data.gouv.fr/datasets/boucles-communales-de-randonnee-de-la-metropole-de-lyon-1",
        "download": "https://www.data.gouv.fr/api/1/datasets/r/3c8d0ecf-961a-4f25-a71f-e2f9f20b1f89",
        "max_routes": 35,
    },
    {
        "id": "calvados-qualite",
        "producer": "Département du Calvados",
        "region": "Normandie",
        "dataset": "https://www.data.gouv.fr/datasets/itineraires-de-randonnee-circuits-qualite-departement-du-calvados",
        "download": "https://www.data.gouv.fr/api/1/datasets/r/8e2dc746-c927-4889-a527-880c05687dd6",
        "max_routes": 35,
    },
    {
        "id": "parc-ecrins",
        "producer": "Parc national des Écrins",
        "region": "Provence-Alpes-Côte d'Azur",
        "dataset": "https://www.data.gouv.fr/datasets/randonnees-du-parc-national-des-ecrins",
        "download": "https://www.data.gouv.fr/api/1/datasets/r/0c62905f-a580-4cee-afc1-5feb9607160d",
        "max_routes": 35,
    },
]
LICENSE = "Licence Ouverte / Open Licence version 2.0"
# Keep downloads strictly scoped to the government dataset IDs above.
ALLOWED_HOSTS = {"www.data.gouv.fr", "data.gouv.fr", "datarmor.cotesdarmor.fr",
                 "data.grandlyon.com", "data.calvados.fr",
                 "rando.ecrins-parcnational.fr", "geotrek.ecrins-parcnational.fr",
                 "geotrek.fr"}

def folded(value: object) -> str:
    t = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()

def haversine(a, b):
    la1,lo1=map(math.radians,a)
    la2,lo2=map(math.radians,b)
    h=math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 12742 * math.asin(min(1,math.sqrt(max(0,h))))  # kilometers

def distance(points):
    return sum(haversine(a,b) for a,b in zip(points,points[1:]))

def attrs(prop, *choices):
    if not isinstance(prop,dict):
        return None
    norm={folded(k).replace("_"," ").replace("-"," ").strip():v for k,v in prop.items()}
    for k in choices:
        value=norm.get(folded(k))
        if value is not None and str(value).strip() and str(value).lower()!="none":
            return value
    for k,v in norm.items():
        if any(x in k for x in ("nom itineraire","nom circuit","nom randonnee","intitule","titre boucle")):
            if v is not None and str(v).strip():return v
    return None

def is_walk(prop):
    activity=attrs(prop,"pratique","activite","activité","activity","sport","mode","types de pratique")
    if activity is None:return True
    name=folded(activity)
    if "pedestr" in name or "marche" in name or "rando" in name or "hiking" in name:
        return True
    if any(x in name for x in ("vtt","velo","cycle","cyclable","cheval","equestre","auto","moto","ski")):
        return False
    return True

def segments(geom):
    if not isinstance(geom,dict):return []
    typ=geom.get("type")
    coords=geom.get("coordinates")
    if typ=="LineString" and isinstance(coords,list):
        return [coords]
    if typ=="MultiLineString" and isinstance(coords,list):
        return coords
    return []

def parse_line(raw):
    if not isinstance(raw,list):return []
    pts=[]
    for p in raw:
        try: lon,lat=float(p[0]),float(p[1])
        except (ValueError,TypeError,IndexError):return []
        if not (math.isfinite(lat) and math.isfinite(lon) and 40.0<=lat<=52.0 and -6.0<=lon<=10.5):
            return []
        ll=[round(lat,6),round(lon,6)]
        if not pts or ll!=pts[-1]:pts.append(ll)
    return pts

def clean_geometry(feature):
    raw_lines=[parse_line(raw) for raw in segments(feature.get("geometry"))]
    lines=[line for line in raw_lines if len(line)>=3]
    if not lines:return None
    # Never invent connections between disconnected MultiLineString segments.
    # Publish only a *complete* single line or a clearly dominant section.
    if len(lines)>1:
        lengths=[distance(line) for line in lines]
        longest=max(range(len(lines)),key=lambda i:lengths[i])
        if sum(lengths) and lengths[longest]/sum(lengths)<0.97:
            return None
        points=lines[longest]
    else:
        points=lines[0]
    steps=[haversine(a,b) for a,b in zip(points,points[1:])]
    if not steps or max(steps)>1.5:return None
    km=sum(steps)
    if not 2.0<=km<=90.0:return None
    return points,km

def simplify(points, max_points=440):
    # Preserve start/end and overall form; no invented points.
    if len(points)<=max_points:return points
    # Ramer-Douglas-Peucker in approximate meters at route latitude.
    center_lat=sum(p[0] for p in points)/len(points)
    ratio=math.cos(math.radians(center_lat))
    def perpendicular(p,a,b):
        ax,ay=a[1]*ratio,a[0]
        bx,by=b[1]*ratio,b[0]
        px,py=p[1]*ratio,p[0]
        vx,vy=bx-ax,by-ay
        t=max(0,min(1,((px-ax)*vx+(py-ay)*vy)/(vx*vx+vy*vy))) if vx*vx+vy*vy else 0
        return math.hypot((px-(ax+t*vx))*111000,(py-(ay+t*vy))*111000)
    def rdp(epsilon):
        keep={0,len(points)-1}
        stack=[(0,len(points)-1)]
        while stack:
            a,b=stack.pop()
            max_dist=-1;index=-1
            for i in range(a+1,b):
                d=perpendicular(points[i],points[a],points[b])
                if d>max_dist:max_dist=d;index=i
            if max_dist>epsilon:
                keep.add(index);stack.append((a,index));stack.append((index,b))
        return [points[i] for i in sorted(keep)]
    for epsilon in (8,12,18,25,35,50,75,100):
        result=rdp(epsilon)
        if len(result)<=max_points:
            return result if abs(distance(result)-distance(points))/distance(points)<0.05 else []
    return []

def normalize(feat,source):
    if not isinstance(feat,dict) or feat.get("type")!="Feature":return None
    prop=feat.get("properties") or {}
    if not is_walk(prop):return None
    raw_name=attrs(prop,"nom","name","nom_du_circuit","nom du circuit",
                    "nom_iti","n_itineraire","nom_itineraire","libelle",
                    "libellé","intitule","titre","randonnee","circuit")
    if not raw_name:return None
    name=re.sub(r"\s+"," ",str(raw_name)).strip()[:155]
    if len(name)<5 or len(name)>155 or folded(name).startswith(("sans nom","unnamed","trace test")):
        return None
    geo=clean_geometry(feat)
    if not geo:return None
    full,km=geo
    simple=simplify(full)
    if len(simple)<3 or abs(km-distance(simple))/km>0.05:return None
    elev=attrs(prop,"denivele_positif","denivele positif","denivele","d_plus","elevation_gain")
    try:
        elevation=int(round(float(str(elev).replace(",",".")))) if elev is not None else 0
        if not 0<=elevation<=15000:elevation=0
    except (ValueError,TypeError):elevation=0
    diff=folded(attrs(prop,"difficulte","difficulté","difficulty") or "")
    difficulty="medium"
    if any(x in diff for x in ("tres facile","facile","easy")):difficulty="easy"
    if "difficile" in diff or "hard" in diff: difficulty="hard"
    if "tres difficile" in diff or "extreme" in diff:difficulty="extreme"
    if "moyen" in diff or "medium" in diff:difficulty="medium"
    loop=haversine(full[0],full[-1])<0.25
    original_id=attrs(prop,"id_source","id","identifiant","objectid","gid") or feat.get("id")
    fingerprint=hashlib.sha256(
        json.dumps([source["id"],str(original_id or ""),name,simple[0],simple[-1]],
                   ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:18]
    key=source["id"]+":"+fingerprint
    disclaimer=("Difficulté non vérifiée par la source. " if not diff else "")
    if elevation==0:disclaimer+="Dénivelé non renseigné (0 ne signifie pas terrain plat). "
    description=(
        f"Itinéraire officiel publié par {source['producer']}. "
        f"{disclaimer}Distance recalculée d'après le tracé GPS, susceptible de varier. "
        f"Source : {source['dataset']} ; licence : {LICENSE}. "
        f"Référence : {key}. Vérifier le balisage et les conditions avant le départ."
    )
    return {
        "source_key":key,"source_name":source["producer"],"source_url":source["dataset"],
        "license":LICENSE,"name":name,"region":source["region"],
        "difficulty":difficulty,"distance":round(km,2),"elevation":elevation,
        "description":description,"route_type":"Boucle" if loop else "Traversée",
        "geometry":{"type":"LineString","coordinates":[[p[1],p[0]] for p in simple]},
    }

def download(source):
    # Resources are whitelisted. No open crawling and no private site scraping.
    res=requests.get(source["download"],timeout=(12,60),
        headers={"User-Agent":"TrekMap-France-Open-Data-Importer/1.0 (public data.gouv.fr datasets)",
                 "Accept":"application/geo+json,application/json,*/*"})
    res.raise_for_status()
    host=urlparse(res.url).hostname or ""
    if host not in ALLOWED_HOSTS and not host.endswith(".ecrins-parcnational.fr"):
        raise ValueError(f"Unexpected upstream host for {source['id']}: {host}")
    if len(res.content)>55*1024*1024:raise ValueError("dataset exceeded 55 MB")
    content=res.json()
    if content.get("type")!="FeatureCollection" or not isinstance(content.get("features"),list):
        raise ValueError("Upstream did not return GeoJSON FeatureCollection")
    return content["features"]

def build():
    stats=Counter()
    routes=[]
    for source in SOURCES:
        try:
            raw=download(source)
            filtered=[]
            for f in raw:
                t=normalize(f,source)
                if t:filtered.append(t)
            by_key={t["source_key"]:t for t in filtered}
            # First usable routes sorted by stable source ID; deterministic reruns.
            chosen=sorted(by_key.values(),key=lambda d:d["source_key"])[:source["max_routes"]]
            routes.extend(chosen)
            stats[source["id"]]=len(chosen)
            print(f"{source['id']}: raw={len(raw)}, geometries_ok={len(filtered)}, chosen={len(chosen)}")
        except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
            print(f"SOURCE ERROR {source['id']}: {type(exc).__name__}: {str(exc)[:250]}",file=sys.stderr)
            stats[source["id"]]=0
    if sum(v>=4 for v in stats.values())<2 or len(routes)<25:
        raise RuntimeError(f"Not enough licensed complete routes: {dict(stats)}")
    output={"version":1,"source_license":LICENSE,
       "sources":[{k:v for k,v in item.items() if k!="download"} for item in SOURCES],
       "stats":dict(stats),"routes":routes}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(output,ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n"
    if not OUT.exists() or OUT.read_text(encoding="utf-8")!=encoded:
        OUT.write_text(encoded,encoding="utf-8")
    print(f"Catalog ready: {len(routes)} routes, {len(encoded)} bytes, "
          f"{len(stats)} sources. Dry-run only, NO database writes.")
    return output

if __name__=="__main__":
    build()
