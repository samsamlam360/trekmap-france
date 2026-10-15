#!/usr/bin/env python3
"""Validate publicly ODbL-licensed complete GR20 GPX, without touching Neon.

The OSM-derived extract is separately attributed/share-alike as ODbL.
"""
import hashlib,json,sys
from pathlib import Path
from xml.etree import ElementTree
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_open_treks as gps
URL="https://mongr20.com/gpx/officiel/gr20-integral-nord-sud.gpx"
LICENSE_URL="https://mongr20.com/traces-gpx-gr20"
DEST=ROOT/"data"/"gr20_osm_open.json"
def build():
    page=requests.get(LICENSE_URL,timeout=30)
    page.raise_for_status()
    lower=page.text.lower()
    if "odbl" not in lower or "openstreetmap" not in lower:
        raise ValueError("Source no longer states ODbL and OSM provenance")
    response=requests.get(URL,timeout=(12,55),
        headers={"User-Agent":"TrekMap-France-ODbL-attributed-GPX-audit/1.0"})
    response.raise_for_status()
    if not (3000<len(response.content)<6_000_000):
        raise ValueError("GR20 unexpected GPX size")
    document=ElementTree.fromstring(response.content)
    points=[]
    for element in document.iter():
        if element.tag.rsplit("}",1)[-1] not in ("trkpt","rtept"):continue
        try:
            lat=float(element.attrib["lat"]);lon=float(element.attrib["lon"])
        except (KeyError,ValueError):continue
        if not (41.28<=lat<=43.10 and 8.4<=lon<=10.0):raise ValueError("Unexpected non-Corsica GPS point")
        value=[round(lat,6),round(lon,6)]
        if not points or points[-1]!=value:points.append(value)
    if len(points)<100:raise ValueError("Insufficient verified track points")
    leaps=[gps.haversine(x,y) for x,y in zip(points,points[1:])]
    if max(leaps)>1.0:raise ValueError("Unexpected GPS discontinuity")
    km=sum(leaps)
    if not (150<=km<=235):raise ValueError(f"Unexpected GPX distance: {km:.1f} km")
    compact=gps.simplify(points,max_points=850)
    if not compact or abs(gps.distance(compact)-km)/km>0.05:
        raise ValueError("Lossy GPX simplification")
    source_hash=hashlib.sha256(response.content).hexdigest()
    key="osm-gr20:"+source_hash[:18]
    route={
      "source_key":key,"source_name":"Mon GR20 / contributeurs OpenStreetMap",
      "source_url":LICENSE_URL,"license":"Open Data Commons ODbL 1.0",
      "name":"GR20 intégral · Calenzana à Conca","region":"Corse",
      "difficulty":"extreme","distance":round(km,2),
      "duration_days":16,"elevation":0,"route_type":"Traversée",
      "description":("Traversée pédestre intégrale du GR20 en Corse, de Calenzana à Conca. "
        "Durée indicative : environ 16 jours selon les étapes classiques, à adapter aux conditions. "
        "Dénivelé non renseigné (0 ne signifie pas terrain plat). "
        "Parcours alpin très exigeant : vérifier météo, névés, refuges, fermetures et variantes officielles avant départ. "
        f"Source GPX et licence : {LICENSE_URL} ; données © les contributeurs OpenStreetMap, "
        "sous licence Open Data Commons ODbL 1.0, attribution et partage à l'identique. "
        f"Référence : {key}."),
      "geometry":{"type":"LineString","coordinates":[[p[1],p[0]] for p in compact]},
      "source_checksum":source_hash,
    }
    DEST.parent.mkdir(exist_ok=True)
    DEST.write_text(json.dumps({"routes":[route],"license":"ODbL 1.0",
       "attribution":"© les contributeurs OpenStreetMap (ODbL), source mongr20.com",
       "source":LICENSE_URL},ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
    print(f"GR20 validated: {km:.1f}km from {len(points)} real points, "
          f"{len(compact)} stored points, max gap {max(leaps):.2f}km; ODbL attributed")
if __name__=="__main__":build()
