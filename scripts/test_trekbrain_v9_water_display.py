"""Regression: water points are map context, never route constraints."""
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_water_display_v9 as water_display


class V3:
    called_items = None

    @staticmethod
    def _route_points_for_candidate(candidate, all_items, intent, forced_via):
        V3.called_items = list(all_items)
        return ([{"name": "Départ"}, {"name": "Arrivée"}], [[]])


class Resources:
    @staticmethod
    def route_safety_report(result, request=None):
        return {
            "safe": False,
            "blockers": [
                "Aucune étape ne dispose d'une information d'eau exploitable alors que l'eau est demandée.",
            ],
            "warnings": ["1 étape(s) ont encore une information d'eau insuffisante."],
        }

    @staticmethod
    def enrich_resources(result):
        out = dict(result)
        out["map_resources"] = {"points": [{"kind": "water", "name": "Fontaine"}]}
        return out


water_display._INSTALLED = False
water_display.install_water_display_only(V3, Resources)

items = [
    {"name": "Fontaine", "category": "water"},
    {"name": "Belvédère", "category": "viewpoint"},
]
V3._route_points_for_candidate(None, items, {}, None)
assert [x["category"] for x in V3.called_items] == ["viewpoint"], V3.called_items

request = SimpleNamespace(require_water=True)
report = Resources.route_safety_report({}, request)
assert report["safe"] is True, report
assert report["blockers"] == [], report
assert report["water_routing_mode"] == "display-only", report
assert any("informatif" in x for x in report["warnings"]), report

enriched = Resources.enrich_resources({})
assert enriched["map_resources"]["water_mode"] == "display-only", enriched
assert enriched["map_resources"]["points"][0]["kind"] == "water", enriched
print("Display-only water resources: OK")
