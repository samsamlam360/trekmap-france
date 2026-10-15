"""Offline regression checks for verified long-distance hiking itineraries."""
from pathlib import Path
from collections import Counter
import json
import math
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"data"/"long_trek_candidates.json"

class LongTrekCatalogTests(unittest.TestCase):
    def test_licensed_long_multiday_trails(self):
        payload=json.loads(PATH.read_text(encoding="utf-8"))
        items=payload["routes"]
        self.assertGreaterEqual(len(items),30, "We must add genuinely useful long hikes")
        self.assertGreaterEqual(sum(t["distance"]>=80 for t in items),10)
        self.assertGreaterEqual(sum(t["distance"]>=120 for t in items),4)
        self.assertGreaterEqual(len({t["source_name"] for t in items}),3)
        keys=set()
        for t in items:
            with self.subTest(name=t["name"]):
                self.assertGreaterEqual(t["distance"],45)
                self.assertLessEqual(t["distance"],280)
                self.assertGreaterEqual(t["duration_days"],2)
                self.assertGreaterEqual(len(t["name"]),4)
                self.assertIn("Licence Ouverte",t["license"])
                self.assertIn(t["source_url"],t["description"])
                self.assertIn(t["source_key"],t["description"])
                self.assertIn("non garantie",t["description"])
                self.assertNotIn(t["source_key"],keys)
                keys.add(t["source_key"])
                self.assertEqual(t["geometry"]["type"],"LineString")
                points=t["geometry"]["coordinates"]
                self.assertGreaterEqual(len(points),3)
                self.assertLessEqual(len(points),900)
                for x,y in points:
                    self.assertTrue(-6<=x<=10.5 and 40<=y<=52,(x,y))
                    self.assertTrue(math.isfinite(x) and math.isfinite(y))
                self.assertFalse(any(bad in t["name"].lower() for bad in ("gravel","en trail","vtt")))
                if t["source_name"]=="Département du Gard":
                    self.assertTrue("gardois" in t["name"] or "gardoise" in t["name"])
        print("Open-data long itineraries:",len(items),
              "by source:",dict(Counter(t["source_name"] for t in items)))

if __name__=="__main__":
    unittest.main(verbosity=2)
