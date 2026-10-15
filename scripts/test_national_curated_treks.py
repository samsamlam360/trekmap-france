"""Validate curated official long trails and separately ODbL licensed OSM routes."""
from pathlib import Path
from collections import Counter
import json,math,unittest

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/"data"/"national_curated_long_treks.json"
OSM=ROOT/"data"/"osm_regional_treks_odbl.json"
REGIONS={
 "Bretagne","Normandie","Pays de la Loire","Centre-Val de Loire",
 "Nouvelle-Aquitaine","Bourgogne-Franche-Comté","Grand Est",
 "Hauts-de-France","Île-de-France","Auvergne-Rhône-Alpes","Corse",
 "Occitanie","Provence-Alpes-Côte d'Azur"
}
def distance(a,b):
    dlat=math.radians(b[1]-a[1])
    dlon=math.radians(b[0]-a[0])
    la1,la2=math.radians(a[1]),math.radians(b[1])
    h=math.sin(dlat/2)**2+math.cos(la1)*math.cos(la2)*math.sin(dlon/2)**2
    return 12742*math.asin(min(1,math.sqrt(h)))
class NationalCuratedTest(unittest.TestCase):
    def test_real_curated_route_geometry(self):
        a=json.loads(OFFICIAL.read_text(encoding="utf-8"))
        b=json.loads(OSM.read_text(encoding="utf-8"))
        official=a["routes"];osm=b["routes"]
        self.assertEqual(len(official),12)
        self.assertEqual(len(osm),8)
        self.assertEqual(b["license"],"Open Data Commons ODbL 1.0")
        self.assertIn("OpenStreetMap",b["attribution"])
        self.assertTrue(all("Licence Ouverte" in x["license"] for x in official))
        self.assertTrue(all(x["license"]=="Open Data Commons ODbL 1.0" for x in osm))
        self.assertTrue({
            "Auvergne-Rhône-Alpes","Centre-Val de Loire",
            "Nouvelle-Aquitaine","Pays de la Loire",
        }.issubset({x["region"] for x in official}))
        self.assertTrue({
            "Bretagne","Bourgogne-Franche-Comté","Grand Est",
            "Hauts-de-France","Île-de-France","Corse",
        }.issubset({x["region"] for x in osm}))
        keys=set()
        for x in official+osm:
            with self.subTest(x=x["name"]):
                self.assertNotIn(x["source_key"],keys)
                keys.add(x["source_key"])
                self.assertIn(x["source_url"],x["description"])
                self.assertIn(x["source_key"],x["description"])
                self.assertIn(x["region"],REGIONS)
                self.assertGreaterEqual(x["duration_days"],1)
                self.assertGreaterEqual(x["distance"],20)
                self.assertGreaterEqual(len(x["name"]),5)
                self.assertEqual(x["geometry"]["type"],"LineString")
                points=x["geometry"]["coordinates"]
                self.assertGreaterEqual(len(points),3)
                self.assertLessEqual(len(points),1150)
                self.assertTrue(all(
                    len(p)==2 and -6.0<=p[0]<=10.5 and 40<=p[1]<=52
                    and all(math.isfinite(v) for v in p) for p in points))
                steps=[distance(l,r) for l,r in zip(points,points[1:])]
                self.assertLessEqual(max(steps),2.5,(x["name"],max(steps)))
                self.assertLessEqual(abs(sum(steps)-x["distance"])/x["distance"],.051)
        print("NATIONAL OPEN TREKS PASS:",len(official),"official,",len(osm),
              "ODbL routes, across",len({x["region"] for x in official+osm}),
              "new-region sets")
if __name__=="__main__":unittest.main(verbosity=2)
