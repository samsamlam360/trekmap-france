#!/usr/bin/env python3
"""Curate *existing* continuous ODbL walking trails in Centre-Val de Loire.

No generated paths, no Neon writes, no cross-region synthetic joins.
Each accepted trail represents a connected real portion of an OSM relation.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,math,sys,requests
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import prepare_open_treks as gps
from collect_osm_regional_treks import longest_real_component

OUT=ROOT/"data"/"centre_multiday_treks_odbl.json"
API="https://hiking.waymarkedtrails.org/api/v1"
HEADERS={"User-Agent":"TrekMap-France/ODbL-Centre-route-verification/1.0"}
TO_GEO=Transformer.from_crs("EPSG:3857","EPSG:4326",always_xy=True)
TO_MERC=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True)
# Geographic envelope encompassing Centre-Val de Loire (wider for border crossings).
BBOX=(0.05,46.45,3.48,48.73)
RELATIONS=[
 (13046192,"GR 31 - Traversée de la Sologne"),
 (13885611,"Tours de Sologne"),
 (15706394,"GR 41 - Vallée du Cher"),
 (7477707,"GR 35 - Du Perche à la Loire"),
 (6439515,"GR 46 - De Tours à Toulouse (tronçon régional)"),
 (13046468,"GR 353 - De Vendôme à la Loire"),
 (13472159,"GR 413 - Du Cher à la Loire"),
 (16446658,"Chemin de Trèves - Vendôme à Tours"),
 (19417626,"Chemin de Trèves - Châteaudun à Vendôme"),
 (8415515,"Via Turonensis par Chartres - Vendôme à Lavardin"),
 (11894574,"Via Turonensis par Chartres - Montigny à Vendôme"),
 (13046466,"GR 353 - variante par Blois"),
 (13046467,"GR 353 - variante Chouzy-sur-Cisse"),
 (13457269,"GR 31 - Sologne Lamotte à La Ferté-Saint-Cyr"),
 (13468382,"GR 31 - Sologne La Ferté-Saint-Cyr à Blois"),
 (2704569,"GR 3 - La Loire sauvage à pied"),
]
merc=(*TO_MERC.transform(BBOX[0],BBOX[1]),*TO_MERC.transform(BBOX[2],BBOX[3]))

REGION_BOUNDARY=json.loads((ROOT/"data"/"centre_val_de_loire_region.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"][0]
def in_centre(pt):
  x,y=pt
  inside=False
  j=len(REGION_BOUNDARY)-1
  for i in range(len(REGION_BOUNDARY)):
    a,b=REGION_BOUNDARY[i],REGION_BOUNDARY[j]
    if ((a[1]>y)!=(b[1]>y)) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
      inside=not inside
    j=i
  return inside

def fetch(rid,title):
  result={"id":rid,"label":title}
  try:
    detail_res=requests.get(f"{API}/details/relation/{rid}",headers=HEADERS,timeout=(10,22))
    detail_res.raise_for_status()
    detail=detail_res.json()
    result["name"]=detail.get("name") or title
    result["official_length_m"]=detail.get("official_length")
    response=requests.get(f"{API}/list/segments",params={"bbox":",".join(f"{x:.2f}" for x in merc),
       "relations":str(rid)},headers=HEADERS,timeout=(12,48))
    response.raise_for_status()
    data=response.json()
    if data.get("type")!="FeatureCollection":raise ValueError("Unexpected geometry format")
    lines=[]
    for item in data.get("features") or []:
      for line in gps.segments(item.get("geometry") or {}):
        coords=[]
        for v in line:
          if len(v)<2:continue
          lon,lat=TO_GEO.transform(float(v[0]),float(v[1]))
          if not (math.isfinite(lon) and math.isfinite(lat)):continue
          coords.append([lon,lat])
        points=gps.parse_line(coords)
        if len(points)>=3:lines.append(points)
    result["features"]=len(data.get("features") or [])
    result["raw_lines"]=len(lines)
    if not lines:
      result["rejected"]="No available hiking line in target bbox";return result
    points,length,components=longest_real_component(lines)
    result["components"]=components
    result["raw_km"]=round(length,2)
    if length<32 or length>330:
      result["rejected"]="Less than 32 km or over 330 km of continuous hiking geometry";return result
    if not all(BBOX[0]-.08<=p[1]<=BBOX[2]+.08 and BBOX[1]-.08<=p[0]<=BBOX[3]+.08 for p in points):
      result["rejected"]="Coordinates outside regional envelope";return result
    compact=gps.simplify(points,max_points=1050)
    actual=gps.distance(compact)
    if len(compact)<3 or abs(actual-length)/length>.04:
      result["rejected"]="Geometry simplification loses more than four percent";return result
    if not all(in_centre([p[1],p[0]]) for p in compact):
      result["rejected"]="Tracé sortant du contour administratif IGN Centre-Val de Loire"
      return result
    steps=[gps.haversine(a,b) for a,b in zip(compact,compact[1:])]
    if max(steps)>2.5:
      result["rejected"]="Suspicious long jump after simplification";return result
    # ISO region is approximate in this clipping step; never claim complete national trail.
    key=f"osm-cvl-rel:{rid}"
    source=f"https://www.openstreetmap.org/relation/{rid}"
    days=max(2,math.ceil(length/20))
    name=(str(detail.get("name") or title).strip()+" · tronçon Centre-Val de Loire")[:153]
    description=(f"Tronçon continu régional cartographié dans OpenStreetMap (relation {rid}). "
      f"Longueur mesurée du tracé représenté : {length:.1f} km. "
      f"Durée estimative : environ {days} jours sur la base de 20 km/jour (non officielle). "
      "Étapes, nuitées, dénivelé, approvisionnement et praticabilité NON vérifiés ; "
      "consulter le balisage et les éventuelles fermetures avant de partir. "
      f"Source : {source}. © les contributeurs OpenStreetMap, licence ODbL 1.0 : "
      "https://www.openstreetmap.org/copyright. "
      f"Référence : {key}.")
    result["accepted"]=True
    result["route"]={"source_key":key,"source_name":"Contributeurs OpenStreetMap / Waymarked Trails",
      "source_url":source,"license":"Open Data Commons ODbL 1.0",
      "name":name,"region":"Centre-Val de Loire",
      "distance":round(length,2),"difficulty":"medium","elevation":0,
      "duration_days":days,"description":description,
      "route_type":"Boucle" if gps.haversine(points[0],points[-1])<.35 else "Traversée",
      "geometry":{"type":"LineString","coordinates":[[v[1],v[0]] for v in compact]}}
    return result
  except Exception as e:
    result["rejected"]=str(e)[:240];return result

def main():
  with ThreadPoolExecutor(max_workers=5) as pool:
    rows=[f.result() for f in as_completed([pool.submit(fetch,*x) for x in RELATIONS])]
  routes=sorted([v["route"] for v in rows if v.get("accepted")],key=lambda r:r["name"])
  for row in rows:row.pop("route",None)
  payload={"license":"Open Data Commons ODbL 1.0",
     "attribution":"© les contributeurs OpenStreetMap, ODbL 1.0",
     "source":"https://hiking.waymarkedtrails.org/",
     "region":"Centre-Val de Loire",
     "policy":"Geographically clipped connected walking segments; no invented paths; estimated days",
     "diagnostics":sorted(rows,key=lambda x:x["label"]),"routes":routes}
  OUT.parent.mkdir(exist_ok=True)
  OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n",encoding="utf-8")
  print("CENTRE VERIFIED",len(routes),"over",len(RELATIONS),"candidate relations",flush=True)
  for x in rows:print(x["id"],x["label"][:32],x.get("raw_km"),x.get("rejected","ACCEPTED"),flush=True)
if __name__=="__main__":main()
