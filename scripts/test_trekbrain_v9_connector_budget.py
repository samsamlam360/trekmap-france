"""Offline HTTP-count and deadline regressions for lodging access checks."""
from copy import deepcopy
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import ors
from backend import trekbrain_circuit_breaker_v9 as breaker
from backend import trekbrain_ors_resilience_v9 as resilience
from backend import trekbrain_route_logistics_v9 as lodging
from backend import trekbrain_speed_v9 as speed


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.payload = payload or {"error": {"message": "No routable connector"}}

    def json(self):
        return deepcopy(self.payload)


class ConnectorBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.0
        self.calls = []
        self.coords = [[45.0, 1.0], [45.0, 1.1]]
        self.legacy = SimpleNamespace(distance_gps=lambda points: 0.2)
        self.stay = {
            "lat": 45.001, "lon": 1.0, "source_url": "https://www.openstreetmap.org/node/1",
            "_night": 1, "_anchor": {"lat": 45.0, "lon": 1.0}, "_anchor_distance_km": 0.12,
        }
        self.options = {1: [self.stay]}
        for target, name, value in ((ors, "ORS_API_KEY", "offline-test-key"),
                                    (ors, "_MATRIX_CACHE", {}),
                                    (resilience, "_CACHE", {}),
                                    (resilience, "_INSTALLED", False),
                                    (breaker, "_INSTALLED", False),
                                    (speed, "_INSTALLED", False)):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_checks(self):
        return lodging._validate_night_options(ors, self.legacy, object(), self.coords, self.options)

    def routed(self, kwargs):
        return Response(200, {"features": [{"geometry": {"coordinates": kwargs["json"]["coordinates"]},
                                           "properties": {"summary": {"distance": 200}}}]})

    def record(self, url, kwargs):
        self.calls.append((url, kwargs["timeout"], self.clock))

    def test_one_matrix_plus_two_direct_legs_share_remaining_http_budget(self):
        def post(url, **kwargs):
            self.record(url, kwargs)
            elapsed = (0.8, 1.0, 0.6)[len(self.calls) - 1]
            self.clock += elapsed
            return Response(400) if url == ors.ORS_MATRIX_URL else self.routed(kwargs)
        with patch.object(time, "monotonic", side_effect=lambda: self.clock), \
                patch.object(ors.requests, "post", side_effect=post), \
                patch.object(ors, "_request_route", side_effect=AssertionError("retry wrappers entered")), \
                patch.object(ors, "get_route", side_effect=AssertionError("general recovery entered")), \
                patch.object(lodging, "ThreadPoolExecutor", side_effect=AssertionError("abandoned worker")):
            result, meta = self.run_checks()
        self.assertTrue(result[lodging._connector_key(self.stay)]["return_validated"])
        self.assertEqual([url for url, _, _ in self.calls], [ors.ORS_MATRIX_URL, ors.ORS_URL, ors.ORS_URL])
        for _, timeout, started in self.calls:
            self.assertIsInstance(timeout, tuple)
            self.assertAlmostEqual(sum(timeout), 104.0 - started)
            self.assertTrue(all(value > 0 for value in timeout))
        self.assertEqual(meta["connector_matrix_calls"], 1)
        self.assertEqual(meta["connector_direction_calls"], 2)

    def test_unroutable_first_leg_does_not_snap_segment_or_try_another_stay(self):
        second = {**self.stay, "lat": 45.002, "source_url": "https://www.openstreetmap.org/node/2"}
        self.options[1].append(second)
        def post(url, **kwargs):
            self.record(url, kwargs)
            return Response(400)
        with patch.object(ors.requests, "post", side_effect=post):
            result, meta = self.run_checks()
        self.assertEqual(result, {})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(meta["connector_direction_calls"], 1)

    def test_matrix_transport_timeout_finishes_synchronously_without_later_retry(self):
        def post(url, **kwargs):
            self.calls.append((url, kwargs["timeout"]))
            time.sleep(sum(kwargs["timeout"]))
            raise ors.requests.Timeout()
        started = time.monotonic()
        with patch.object(lodging, "_CONNECTOR_BUDGET_SECONDS", 0.03), \
                patch.object(ors.requests, "post", side_effect=post), \
                patch.object(lodging, "ThreadPoolExecutor", side_effect=AssertionError("abandoned worker")):
            result, meta = self.run_checks()
            returned = time.monotonic()
            time.sleep(0.035)
        self.assertLess(returned - started, 0.15)
        self.assertEqual(result, {})
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(meta["connector_budget_exhausted"])
        self.assertEqual(meta["connector_direction_calls"], 0)

    def test_first_direction_consuming_deadline_cannot_start_return_leg(self):
        def post(url, **kwargs):
            self.record(url, kwargs)
            if url == ors.ORS_MATRIX_URL:
                self.clock += 0.2
                return Response(400)
            self.clock += sum(kwargs["timeout"])
            raise ors.requests.Timeout()
        with patch.object(time, "monotonic", side_effect=lambda: self.clock), \
                patch.object(ors.requests, "post", side_effect=post):
            result, meta = self.run_checks()
        self.assertEqual(result, {})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(meta["connector_direction_calls"], 1)
        self.assertTrue(meta["connector_budget_exhausted"])

    def test_expired_budget_makes_zero_http_calls(self):
        with patch.object(lodging, "_CONNECTOR_BUDGET_SECONDS", 0), patch.object(ors.requests, "post") as post:
            result, meta = self.run_checks()
        self.assertEqual(result, {})
        self.assertEqual(meta["connector_matrix_calls"], 0)
        self.assertEqual(meta["connector_direction_calls"], 0)
        post.assert_not_called()

    def test_positive_matrix_and_directions_caches_remain_shared_and_copied(self):
        def post(url, **kwargs):
            self.record(url, kwargs)
            if url == ors.ORS_MATRIX_URL:
                return Response(200, {"distances": [[0, 0.2], [0.2, 0]]})
            return self.routed(kwargs)
        points = [[45.0, 1.0], [45.001, 1.0]]
        with patch.object(ors.requests, "post", side_effect=post), patch.object(resilience, "_INSTALLED", True):
            matrix = ors.get_distance_matrix_bounded(points, timeout_s=1)
            matrix["distances"][0][1] = 99
            reused = ors.get_distance_matrix(points)
            self.assertEqual(reused["distances"][0][1], 0.2)
            routed = ors.get_route_direct_bounded(points, self.legacy.distance_gps, timeout_s=1)
            routed["coords"][0][0] = 99
            cached = ors.get_route_direct_bounded(points, self.legacy.distance_gps, timeout_s=1)
            self.assertEqual(cached["coords"][0][0], 45.0)
            self.assertTrue(cached["route_cache"])
        self.assertEqual(len(self.calls), 2)

    def test_bounded_calls_observe_shared_quota_and_matrix_auth_cooldowns(self):
        points = [[45.0, 1.0], [45.001, 1.0]]
        with patch.object(breaker, "_INSTALLED", True), \
                patch.object(breaker, "_STATE", {"ors": 0.0, "matrix": 0.0, "overpass": 0.0}), \
                patch.object(breaker, "_RATE_LIMITED_UNTIL", {"ors": 0.0, "matrix": 0.0}), \
                patch.object(speed, "_INSTALLED", True), \
                patch.object(speed, "_MATRIX_AUTH_STATE", {"until": 0.0, "status": None}), \
                patch.object(ors.requests, "post", side_effect=[Response(429), Response(403)]) as post:
            first = ors.get_route_direct_bounded(points, self.legacy.distance_gps, timeout_s=1)
            second = ors.get_route_direct_bounded(points, self.legacy.distance_gps, timeout_s=1)
            self.assertTrue(first["fallback"] and second["fallback"])
            self.assertEqual(post.call_count, 1)
            first_matrix = ors.get_distance_matrix_bounded(points, timeout_s=1)
            second_matrix = ors.get_distance_matrix_bounded(points, timeout_s=1)
            self.assertTrue(first_matrix["fallback"] and second_matrix["fallback"])
            self.assertEqual(post.call_count, 2)
            self.assertIn("403", second_matrix["warning"])


if __name__ == "__main__":
    unittest.main()
