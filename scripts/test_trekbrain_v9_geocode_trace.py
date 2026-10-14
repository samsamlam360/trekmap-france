"""Network-free qualification, provider evidence and request-scope isolation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from backend import free_planner_v2 as geo
from backend import trekbrain_geo_fallback_v9 as geocoding
from backend import trekbrain_request_v9 as request
from backend import trekbrain_request_overlay_v9 as overlay


def feature(name, lon, lat, code="39", score=.9):
    return {"geometry": {"coordinates": [lon, lat]},
            "properties": {"toponym": name, "depcode": [code], "score": score}}


class GeocodeEvidenceTests(unittest.TestCase):
    def test_geocoder_query_excludes_trail_instructions_not_area_qualifiers(self):
        self.assertEqual(
            request._clean_place("Saintes-Maries-de-la-Mer sans marcher dans l'eau"),
            "Saintes-Maries-de-la-Mer",
        )
        self.assertEqual(
            request._clean_place("Sainte-Enimie et des gorges du Tarn"),
            "Sainte-Enimie",
        )
        self.assertEqual(
            request._clean_place("Lac Blanc dans les Vosges"),
            "Lac Blanc dans les Vosges",
            "Do not erase an explicitly written geographic disambiguator",
        )

    def test_provider_identity_prevents_town_centroid_ambiguity(self):
        # A city place node must outrank its administrative boundary centroid
        # without authorizing arbitrary similarly named roads or other towns.
        raw = [
            {"display_name": "Dijon, Côte-d'Or, Bourgogne-Franche-Comté, France",
             "lat": "47.3215806", "lon": "5.0414701",
             "osm_type": "node", "class": "place", "type": "city"},
            {"display_name": "Dijon, Côte-d'Or, Bourgogne-Franche-Comté, France",
             "lat": "47.408796", "lon": "5.0646164",
             "osm_type": "relation", "class": "boundary", "type": "administrative"},
        ]
        with patch.object(geo, "_request_json", return_value=raw):
            evidence = geo._geocode_nominatim("Dijon, France")
        self.assertEqual(evidence[0]["geocode_osm_type"], "node")
        selected = geocoding.filter_provider_places("Dijon, France", evidence, "nominatim")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["geocode_osm_type"], "node")
        self.assertEqual(
            geocoding.filter_provider_places("Dijon, France", [
                {**row, "geocode_osm_type": "relation"} for row in evidence
            ], "nominatim"), [], "No node means no arbitrary centroid choice"
        )

    def test_region_hint_filters_real_provider_evidence_not_fake_centres(self):
        lake1 = geo._normalise_place("Lac des Settons, Nièvre, France", 47.1827, 4.0662)
        lake2 = geo._normalise_place("Lac des Settons, Nièvre, France", 47.1748, 4.0741)
        wrong = geo._normalise_place("Lac des Settons, Autre lieu, France", 48.1, 6.4)
        chosen = geocoding.filter_provider_places(
            "Lac des Settons, Morvan, France", [lake1, lake2, wrong], "nominatim"
        )
        self.assertEqual(len(chosen), 2)
        self.assertTrue(all(abs(p["lat"] - 47.18) < .02 for p in chosen))
        self.assertEqual(
            geocoding.filter_provider_places(
                "Lac des Settons, Haut-Rhin, France", [lake1, lake2], "nominatim"), []
        )
        self.assertEqual(
            geocoding.filter_provider_places(
                "Lac des Settons, Morvan, France", [wrong], "nominatim"), []
        )

    def test_two_real_distant_named_nodes_are_still_ambiguous(self):
        def town(lat, lon):
            return {**geo._normalise_place("Nantua, Ain, France", lat, lon),
                    "geocode_osm_type": "node", "geocode_osm_class": "place",
                    "geocode_osm_subtype": "town"}
        self.assertEqual(
            geocoding.filter_provider_places("Nantua, Ain, France",
                                            [town(46.15, 5.60), town(46.24, 5.70)],
                                            "nominatim"), []
        )

    def test_explicit_qualifier_survives_provider_web_title(self):
        prompt = "Une boucle de randonnée autour des Cascades de la Rivière, Jura, avec un gîte."
        places = request._extract_prompt_places(prompt)
        self.assertEqual(places[0]["place"], "Cascades de la Rivière, Jura")
        calls = []

        def provider(query):
            calls.append(query)
            return [geo._normalise_place("Site officiel des Cascades, Maison du tourisme", 46.7, 5.8)]

        data = geo.AIPlanRequest(prompt=prompt, region="Chartres")
        with patch.object(geo, "_geocode", provider):
            effective, meta = request.reconcile_request(data)
        self.assertEqual(effective.region, "Cascades de la Rivière, Jura")
        self.assertEqual(meta["geographic_qualifier"], "Jura")
        self.assertEqual(calls, ["Cascades de la Rivière, Jura, France"])
        # A qualified written request stays authoritative during an outage.
        with patch.object(geo, "_geocode", return_value=[]):
            effective, meta = request.reconcile_request(data)
        self.assertEqual(effective.region, "Cascades de la Rivière, Jura")
        self.assertEqual(meta["reason"], "explicit-qualified-area-deferred-geocode")
        self.assertFalse(any(
            "," in place["place"]
            for place in request._extract_prompt_places("Randonnée autour du lac Test, avec de l'eau.")
        ))

    def test_ign_rejects_explain_department_name_score_and_coordinates(self):
        payload = {"features": [
            feature("Lac du Test", 5.8, 46.7),
            feature("Lac du Test", 7.0, 48.0, code="68"),
            feature("Lac Autre", 5.8, 46.7),
            feature("Lac du Test", 5.8, 46.7, score=.2),
            feature("Lac du Test", 500, 46.7),
        ]}

        def provider(url, **kwargs):
            if url == geocoding.DEPARTMENTS_URL:
                return [{"nom": "Jura", "code": "39"}]
            return payload

        token = geocoding.begin_geocode_trace()
        try:
            with patch.object(geo, "_request_json", provider):
                rows = geocoding.geocode_ign_poi("Lac du Test, Jura")
            trace = geocoding.geocode_trace_snapshot()
            self.assertEqual(len(rows), 1)
            reasons = {entry["reason"] for entry in trace["queries"] if not entry["accepted"]}
            self.assertTrue({"wrong_department", "name_mismatch", "low_score", "invalid_coordinates"} <= reasons)
            good = next(entry for entry in trace["queries"] if entry["accepted"])
            self.assertEqual(good["provider"], "ign-bdtopo-poi")
            self.assertEqual(good["coordinates"], [46.7, 5.8])
            self.assertEqual(good["department_code"], "39")
            self.assertEqual(good["department"], "Jura")
            # Exported JSON evidence must not be a mutable view of the scope.
            good["coordinates"][0] = 0
            self.assertEqual(next(x for x in geocoding.geocode_trace_snapshot()["queries"] if x["accepted"])["coordinates"], [46.7, 5.8])
        finally:
            geocoding.end_geocode_trace(token)

    def test_two_homonyms_in_same_department_are_not_ranked_by_score(self):
        payload = {"features": [feature("Lac du Test", 5.8, 46.7),
                                feature("Lac du Test", 5.9, 47.0, score=.99)]}
        token = geocoding.begin_geocode_trace()
        try:
            with patch.object(geo, "_request_json", return_value=payload):
                self.assertEqual(geocoding.geocode_ign_poi("Lac du Test, 39"), [])
            self.assertEqual({x["reason"] for x in geocoding.geocode_trace_snapshot()["queries"]}, {"ambiguous_homonyms"})
        finally:
            geocoding.end_geocode_trace(token)

    def test_fast_geocoder_reaches_ign_instead_of_wrong_department_or_region_centre(self):
        from backend import smart_planner_v3 as v3, smart_planner_v5 as v5, smart_planner_v9 as v9
        from backend import trekbrain_commune_fallback_v9 as communes, trekbrain_speed_v9 as speed
        speed.install_fast_planning(v3, v5, v9)
        query = "Cascades de la Rivière, Jura, France"
        wrong = geo._normalise_place("Cascades de la Rivière, Haut-Rhin, France", 48.0, 7.0)

        def provider(url, **kwargs):
            if url == geocoding.DEPARTMENTS_URL:
                return [{"nom": "Jura", "code": "39"}]
            return {"features": [feature("Cascades de la Rivière", 5.8, 46.7)]}

        token = geocoding.begin_geocode_trace()
        try:
            with patch.object(geo, "_geocode_nominatim", return_value=[wrong]), \
                    patch.object(geo, "_geocode_photon", return_value=[]) as photon, \
                    patch.object(geocoding, "geocode_ign", return_value=[]), \
                    patch.object(communes, "geocode_commune", return_value=[]), \
                    patch.object(geo, "_request_json", provider), \
                    patch.object(speed, "_NOMINATIM_COOLDOWN_UNTIL", 0):
                rows = v3._geocode(query)
            self.assertEqual(photon.call_count, 1)
            self.assertEqual(rows[0]["geocode_provider"], "ign-bdtopo-poi")
            trace = geocoding.geocode_trace_snapshot()["queries"]
            self.assertTrue(any(x["reason"] == "department_not_confirmed" and x["provider"] == "nominatim" for x in trace))
            self.assertTrue(any(x["reason"] == "regional_centre_is_not_requested_place" for x in trace))
            selected = [x for x in trace if x.get("selected")]
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["provider"], "ign-bdtopo-poi")
            self.assertEqual(selected[0]["coordinates"], [46.7, 5.8])
        finally:
            geocoding.end_geocode_trace(token)

    def _endpoint(self, barrier=None):
        app = FastAPI()

        class Legacy:
            @staticmethod
            def current_user():
                return {"id": 0}

        @app.post("/ai/plan")
        def plan(data, user):
            if data.region != "Empty place":
                geocoding.record_geocode(data.region, "fixture-provider", accepted=True,
                                          reason="resolved", selected=True,
                                          point={"name": data.region, "lat": 46.7, "lon": 5.8})
            if barrier:
                barrier.wait(timeout=5)
            if data.region == "Failure place":
                raise HTTPException(422, "Ambiguous geography")
            return {}

        overlay._wrap_post(app, "/ai/plan", Legacy, add_note=False)
        return next(route.endpoint for route in app.routes if route.path == "/ai/plan")

    def test_overlay_exports_failed_trace_and_resets_nested_scope(self):
        endpoint = self._endpoint()
        token = geocoding.begin_geocode_trace()
        geocoding.record_geocode("Parent place", "parent", accepted=True, reason="resolved")
        try:
            with patch.object(overlay, "_effective_payload", side_effect=lambda data: (data, {})):
                with self.assertRaises(HTTPException) as caught:
                    endpoint(geo.AIPlanRequest(prompt="A hiking request", region="Failure place"), {"id": 0})
                evidence = caught.exception.detail["request_resolution"]["geocoding"]["queries"]
                self.assertEqual([x["query"] for x in evidence], ["Failure place"])
                result = endpoint(geo.AIPlanRequest(prompt="A hiking request", region="Empty place"), {"id": 0})
                self.assertEqual(result["request_resolution"]["geocoding"]["queries"], [])
            self.assertEqual([x["query"] for x in geocoding.geocode_trace_snapshot()["queries"]], ["Parent place"])
        finally:
            geocoding.end_geocode_trace(token)
        self.assertEqual(geocoding.geocode_trace_snapshot()["queries"], [])

    def test_concurrent_requests_keep_separate_provider_evidence(self):
        endpoint = self._endpoint(Barrier(2))

        def invoke(region):
            result = endpoint(geo.AIPlanRequest(prompt="A hiking request", region=region), {"id": 0})
            self.assertEqual(geocoding.geocode_trace_snapshot()["queries"], [])
            return result["request_resolution"]["geocoding"]["queries"]

        with patch.object(overlay, "_effective_payload", side_effect=lambda data: (data, {})):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(invoke, region) for region in ("First place", "Second place")]
                traces = [future.result(timeout=5) for future in futures]
        self.assertEqual([[entry["query"] for entry in trace] for trace in traces],
                         [["First place"], ["Second place"]])


if __name__ == "__main__":
    unittest.main()
