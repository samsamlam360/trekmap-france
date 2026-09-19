"""Offline regressions: no network, API keys or production database needed."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time
import unittest
from unittest.mock import patch

from backend import smart_planner_v9 as planner, web_research_v9 as web
from backend.free_planner_v2 import AIPlanRequest
from backend.trekbrain_dialogue_v9 import AskRequest, answer
from backend.trekbrain_runtime_v9 import free_mode, seconds


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.request = AIPlanRequest(prompt="Boucle dans le Vercors", region="Vercors", days=2, daily_km=15,
                                     require_transit=False, require_water=False, require_accommodation=False)
        self.plan = {"stages": [{"distance_km": 15}, {"distance_km": 15}], "duration_days": 2,
                     "confidence": {"score": 90}, "start": {"lat": 45, "lon": 5}, "end": {"lat": 45, "lon": 5},
                     "route_preview": {"fallback": False, "coords": [[45, 5], [45.01, 5.01]], "distance_km": 30}}

    def audit(self, features=None, compound=None):
        return planner.precision_audit(self.plan, self.request, features or {}, {}, compound or {})

    def test_missing_geometry_is_not_confirmed(self):
        self.plan["route_preview"] = {}
        self.assertIn("routage dégradé", self.audit()["blockers"])
        self.assertLess(self.audit()["score"], 60)

    def test_invalid_coordinates(self):
        self.plan["start"]["lat"] = float("nan")
        self.assertIn("fermeture de boucle invérifiable", self.audit()["blockers"])

    def test_loop_is_not_three_kilometres_open(self):
        self.plan["end"]["lat"] = 45.02
        self.assertIn("boucle mal refermée", self.audit()["blockers"])

    def test_missing_stages_not_duration_metadata(self):
        self.plan["stages"] = []
        self.assertIn("durée différente de la demande", self.audit()["blockers"])

    def test_nonfinite_distance(self):
        self.plan["stages"][0]["distance_km"] = float("nan")
        self.assertIn("distances manquantes ou invalides", self.audit()["blockers"])

    def test_prompt_overrides_form_defaults(self):
        self.request = self.request.model_copy(update={"days": 3, "prompt": "Boucle dans le Vercors sur 2 jours"})
        self.assertNotIn("durée différente de la demande", self.audit()["blockers"])

    def test_hard_maximum(self):
        self.request = self.request.model_copy(update={"prompt": "Vercors max 12 km par jour"})
        self.assertIn("distance maximale dépassée", self.audit()["blockers"])

    def test_missing_required_objective(self):
        audit = self.audit(compound={"side_requests": [{"kind": "castle", "text": "château requis", "required": True}]})
        self.assertIn("objectif secondaire important non satisfait", audit["blockers"])

    def test_wrong_day_not_satisfied(self):
        req = {"kind": "castle", "text": "château au jour 2", "preferred_day": 2}
        self.plan["side_requests"] = [{"kind": "castle", "request": req["text"], "satisfied": True, "route_day": 1}]
        self.assertTrue(self.audit(compound={"side_requests": [req]})["blockers"])

    def test_enriched_objective_text_does_not_fail_matching(self):
        req = {"kind": "castle", "text": "château au jour 2", "preferred_day": 2}
        self.plan["side_requests"] = [{"kind": "castle", "request": "texte enrichi par le moteur", "satisfied": True, "route_day": 2}]
        self.assertNotIn("objectif secondaire important non satisfait", self.audit(compound={"side_requests": [req]})["blockers"])

    def test_transport_missing_return(self):
        self.plan["transport"] = {"outbound": "Gare A"}
        self.assertIn("accès en transport non renseigné", self.audit({"transit": 1})["blockers"])


class FreeModeTests(unittest.TestCase):
    def test_personalization_failure_does_not_prevent_plan(self):
        with patch.object(planner, "model_for_user", side_effect=RuntimeError("offline")):
            state, _, _ = planner._model_for_user_cached(None, 918273)
            self.assertFalse(state["learning_available"])
            self.assertTrue(planner.rank_actions(state, {"bias": 1}))

    @patch.dict("os.environ", {"TREKBRAIN_FREE_MODE": "1", "GEMINI_API_KEY": "not-a-real-key"})
    def test_key_does_not_enable_paid_brain(self):
        with patch.object(planner.v7, "analyze_request", side_effect=AssertionError("paid call")):
            data = AIPlanRequest(prompt="Randonnée dans le Vercors", region="Vercors")
            self.assertIsNone(planner._analysis_for(data)[2])
            self.assertFalse(planner._brain_enabled())

    @patch.dict("os.environ", {"TREKBRAIN_FREE_MODE": "1"})
    def test_search_bypasses_paid_providers(self):
        with patch.object(web.base, "search_web", side_effect=AssertionError("paid search")), patch.object(web.base, "_duckduckgo_search", return_value=[]) as search:
            web._run_query("Vercors", True)
            search.assert_called_once()

    def test_invalid_budget_uses_default(self):
        with patch.dict("os.environ", {"TEST_SECONDS": "nan"}):
            self.assertEqual(seconds("TEST_SECONDS", 8), 8)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        with web._LOCK:
            web._CACHE.clear()

    def test_host_not_path_controls_rank(self):
        genuine = web.source_score({"url": "https://www.sncf.com/"})
        for url in ["https://fake.example/sncf.com/", "https://sncf.com.fake.example/"]:
            self.assertGreater(genuine, web.source_score({"url": url}))

    def test_dedup_preserves_event_ids(self):
        a = web._canonical_url("https://example.org/event?id=1&utm_source=test#top")
        self.assertEqual(a, "https://example.org/event?id=1")
        self.assertNotEqual(a, web._canonical_url("https://example.org/event?id=2"))
        self.assertEqual(web._canonical_url("javascript:alert(1)"), "")

    def test_cache_and_no_page_fetch(self):
        result = ("unique", [{"url": "https://example.org/", "title": "Vercors", "snippet": "piste"}])
        with patch.object(web, "_select_queries", return_value=["unique"]), patch.object(web, "_run_query", return_value=result) as query, patch.object(web.base, "fetch_page_summary", side_effect=AssertionError("blind fetch")):
            first = web.research_request("p", "l", {})
            # The callback may still be finishing after future.result().
            with web._LOCK:
                future = web._PENDING.get((free_mode(), "unique"))
            if future:
                future.result()
            second = web.research_request("p", "l", {})
            self.assertEqual(query.call_count, 1)
            self.assertFalse(first["claims_verified"])
            self.assertEqual(second["results"][0]["evidence_type"], "search_snippet")

    def test_deadline_and_bounded_shared_work(self):
        release, entered = Event(), Event()
        def slow(q, free):
            entered.set()
            release.wait(2)
            return q, []
        try:
            with patch.object(web, "_select_queries", return_value=["slow-unique"]), patch.object(web, "_run_query", side_effect=slow) as query, patch.object(web, "seconds", return_value=0.03):
                start = time.monotonic()
                result = web.research_request("p", "l", {})
                self.assertLess(time.monotonic() - start, 0.5)
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["timed_out_queries"], 1)
                self.assertTrue(entered.wait(0.5))
                web.research_request("p", "l", {})
                self.assertEqual(query.call_count, 1)
        finally:
            release.set()
            with web._LOCK:
                pending = list(web._PENDING.values())
            for future in pending:
                future.result(timeout=2)


class DialogueTests(unittest.TestCase):
    def test_specific_day(self):
        data = AskRequest(question="Eau au jour 2 ?", stages=[{"water_notes": "Fontaine A"}, {"water_notes": "Source B"}])
        reply = answer(data)
        self.assertIn("Source B", reply["answer"])
        self.assertNotIn("Fontaine A", reply["answer"])
        self.assertFalse(reply["verified_live"])

    def test_unknown_day(self):
        self.assertIn("n'existe pas", answer(AskRequest(question="jour 8 ?"))["answer"])

    def test_missing_hours_not_invented(self):
        reply = answer(AskRequest(question="Quels horaires de train ?"))
        self.assertIn("Aucun horaire", reply["answer"])

    def test_general_question_is_honest(self):
        self.assertIn("pas un assistant généraliste", answer(AskRequest(question="Écris un roman"))["answer"])


class PipelineTests(unittest.TestCase):
    @patch.dict("os.environ", {"TREKBRAIN_FREE_MODE": "1"})
    def test_shared_context_and_optional_learning(self):
        data = AIPlanRequest(prompt="Boucle dans le Vercors", region="Vercors", days=2, daily_km=15)
        shared = {"normalized": data.prompt, "compound": {}, "brain": None, "questions": [],
                  "base_prompt": data.prompt, "research": {"results": [], "evidence": {}}, "prepare_ms": 1}
        state = planner._state_template()
        ranked = planner.rank_actions(state, {"bias": 1})[:2]
        quality1 = {"score": 55, "blockers": ["tracé"], "grade": "fragile", "reasons": [], "needs_reflection": True}
        quality2 = {"score": 75, "blockers": [], "grade": "à vérifier", "reasons": [], "needs_reflection": False}
        with patch.object(planner, "_learning_context", return_value=(data.prompt, {}, {}, ranked, state, {}, {})), \
             patch.object(planner, "_prepare_shared", return_value=shared) as prepare, \
             patch.object(planner, "_run_hypothesis", side_effect=[({}, quality1, 1), ({}, quality2, 1)]) as run, \
             patch.object(planner, "create_episode", side_effect=RuntimeError("offline")), \
             patch.object(planner.v7, "critique_plan", side_effect=AssertionError("paid critique")):
            result = planner._build(data, None, 1)
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(run.call_count, 2)
            self.assertIs(run.call_args_list[0].args[4], run.call_args_list[1].args[4])
            self.assertEqual(result["trekbrain"]["strategy"], ranked[1]["action"])
            self.assertIsNone(result["learning_token"])
            self.assertEqual(result["agent"]["performance"]["gemini_audits"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
