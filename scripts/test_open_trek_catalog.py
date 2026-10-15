"""Offline quality gate for the open-data import. No network and no Neon writes."""
from pathlib import Path
import json
import math
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"data"/"catalogue_open_treks.json"
FRANCE=(40.,52.,-6.,10.5)

class CatalogCheck(unittest.TestCase):
    def test_catalogue(self):
        self.assertTrue(PATH.is_file(),"Importer did not create a source catalogue")
        catalog=json.loads(PATH.read_text(encoding="utf-8"))
        self.assertEqual(catalog["version"],1)
        routes=catalog["routes"]
        self.assertGreaterEqual(len(routes),25)
        self.assertGreaterEqual(sum(v>=4 for v in catalog["stats"].values()),2)
        keys=set()
        for route in routes:
            with self.subTest(route=route["name"]):
                key=route["source_key"]
                self.assertNotIn(key,keys)
                keys.add(key)
                self.assertEqual(route["geometry"]["type"],"LineString")
                points=route["geometry"]["coordinates"]
                self.assertGreaterEqual(len(points),3)
                self.assertLessEqual(len(points),440)
                self.assertTrue(all(len(p)==2 and -6<=p[0]<=10.5 and 40<=p[1]<=52 for p in points))
                self.assertTrue(all(math.isfinite(v) for p in points for v in p))
                self.assertGreaterEqual(route["distance"],2)
                self.assertLessEqual(route["distance"],90)
                self.assertLessEqual(len(route["name"]),155)
                self.assertIn(route["region"],{
                    "Bretagne","Normandie","Auvergne-Rhône-Alpes","Provence-Alpes-Côte d'Azur","Occitanie"})
                self.assertIn(route["difficulty"],{"easy","medium","hard","extreme"})
                self.assertIn("Licence Ouverte",route["description"])
                self.assertIn(route["source_url"],route["description"])
                self.assertIn(key,route["description"])
                self.assertTrue(route["source_url"].startswith("https://www.data.gouv.fr/datasets/"))

if __name__=="__main__":
    unittest.main(verbosity=2)
