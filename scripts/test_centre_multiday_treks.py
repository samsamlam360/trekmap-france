"""Non-destructive validation of ODbL multi-day hikes in Centre-Val de Loire."""
from pathlib import Path
import json, math, unittest

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"data"/"centre_multiday_treks_odbl.json"
BOUNDARY=ROOT/"data"/"centre_val_de_loire_region.geojson"
EXPECTED={13046192,13885611,15706394,6439515,13046468,
          13472159,16446658,11894574,13457269}

def inside(p,ring):
    x,y=p
    valid=False
    j=len(ring)-1
    for i,a in enumerate(ring):
        b=ring[j]
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            valid=not valid
        j=i
    return valid

def km(a,b):
    lat1,lat2=math.radians(a[1]),math.radians(b[1])
    dl=math.radians(b[0]-a[0]);da=math.radians(b[1]-a[1])
    h=math.sin(da/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dl/2)**2
    return 12742*math.asin(min(1,math.sqrt(h)))

class CentreLongTreks(unittest.TestCase):
    def test_curated(self):
        payload=json.loads(FILE.read_text(encoding="utf-8"))
        bounds=json.loads(BOUNDARY.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"][0]
        self.assertIn("ODbL",payload["license"])
        self.assertIn("OpenStreetMap",payload["attribution"])
        self.assertEqual(len(payload["routes"]),len(EXPECTED))
        existing=set()
        for r in payload["routes"]:
            with self.subTest(route=r["name"]):
                self.assertEqual(r["region"],"Centre-Val de Loire")
                self.assertGreater(r["duration_days"],1)
                self.assertGreaterEqual(r["distance"],32)
                self.assertLessEqual(r["distance"],330)
                self.assertEqual(r["elevation"],0)
                self.assertIn("Dénivelé",r["description"])
                self.assertIn("NON vérifiés",r["description"])
                self.assertIn("OpenStreetMap",r["description"])
                self.assertIn(r["source_url"],r["description"])
                self.assertIn(r["source_key"],r["description"])
                self.assertNotIn(r["source_key"],existing)
                existing.add(r["source_key"])
                self.assertEqual(r["geometry"]["type"],"LineString")
                pts=r["geometry"]["coordinates"]
                self.assertGreaterEqual(len(pts),10)
                self.assertLessEqual(len(pts),1050)
                self.assertTrue(all(inside(p,bounds) for p in pts))
                steps=[km(a,b) for a,b in zip(pts,pts[1:])]
                self.assertLessEqual(max(steps),2.5)
                self.assertLessEqual(abs(sum(steps)-r["distance"])/r["distance"],.041)
        ids={int(r["source_key"].split(":")[1]) for r in payload["routes"]}
        self.assertEqual(ids,EXPECTED)
        self.assertNotIn(13481848,ids,"the GR32 line is mostly in Ile-de-France")
        self.assertNotIn(1562017,ids,"avoid the fully overlapping Sologne segment")
        print("CENTRE LONG TREKS VERIFIED:",len(payload["routes"]),
              "real regional footpaths strictly exceeding one day")

if __name__=="__main__":unittest.main(verbosity=2)
