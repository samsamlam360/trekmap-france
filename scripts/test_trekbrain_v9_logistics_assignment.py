"""Offline regressions for stage-end lodging, access evidence and provider caps."""
from copy import deepcopy
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import trekbrain_roundtrip_v9 as route
from backend import trekbrain_route_logistics_v9 as lodging
from backend import trekbrain_route_logistics_guard_v9 as guard


class Router:
    def __init__(self, unavailable=(), forward_only=()):
        self.unavailable = set(unavailable)
        self.forward_only = set(forward_only)
        self.matrix_calls = []
        self.route_calls = []

    @staticmethod
    def key(point):
        return tuple(round(float(value), 6) for value in point)

    def get_distance_matrix(self, points):
        self.matrix_calls.append(deepcopy(points))
        rows = []
        for a in points:
            cells = []
            for b in points:
                ka, kb = self.key(a), self.key(b)
                blocked = ka != kb and (ka in self.unavailable or kb in self.unavailable
                                         or ka in self.forward_only)
                cells.append(None if blocked else route._haversine(a, b) * 1.1)
            rows.append(cells)
        return {"distances": rows, "fallback": False, "profile": "foot-hiking"}

    def get_route(self, points, distance_gps):
        self.route_calls.append(deepcopy(points))
        return {"coords": points, "distance": 0.0, "fallback": True}


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.coords = [[45.0, 1.0], [45.0, 1.3]]
        self.total = route._cumulative(self.coords)[-1]
        self.legacy = SimpleNamespace(distance_gps=lambda coords: route._cumulative(coords)[-1])

    def stay(self, anchor, name, offset=0.001, source=None):
        return {"name": name, "lat": anchor["lat"] + offset, "lon": anchor["lon"],
                "category": "refuge", "source_url": source or f"osm://{name}"}

    def attach(self, lengths, stays, router, strict=False):
        days = len(lengths)
        result = {
            "route_preview": {"coords": deepcopy(self.coords), "distance_km": self.total,
                              "fallback": False},
            "stages": [{"day": i + 1, "distance_km": km} for i, km in enumerate(lengths)],
            "planner": {}, "advisor_notes": [],
        }
        before = deepcopy(result)
        projected = lodging._project_stays(route, self.coords, stays, "refuge", 6.0)
        meta = {"terrain_rows": [], "terrain_preloaded": False}
        data = SimpleNamespace(days=days, daily_km=10, prompt="Tout à pied sans transfert" if strict else "")
        with patch.object(lodging, "_discover_stays", return_value=([], projected, meta)):
            lodging._attach_logistics(result, data, self.legacy, object(), route, object(), router,
                                     {"days": days, "daily_target": 10, "daily_max": 15}, "refuge")
        self.assertEqual(result["route_preview"], before["route_preview"])
        self.assertEqual([s["distance_km"] for s in result["stages"]], lengths)
        return result

    def test_sparse_unequal_stages_use_true_ends_for_photon_and_connectors(self):
        lengths = [4.0, 10.0, self.total - 14.0]
        anchors = lodging._night_anchors(route, self.coords, 3,
                                        [{"distance_km": value} for value in lengths])
        self.assertAlmostEqual(anchors[0]["route_progress_km"], 4.0)
        self.assertAlmostEqual(anchors[1]["route_progress_km"], 14.0)
        self.assertAlmostEqual(anchors[0]["lon"], 1 + 0.3 * 4 / self.total)
        calls = []
        def lookup(anchor, *args, **kwargs):
            calls.append(dict(anchor))
            return self.stay(anchor, str(anchor["night"]))
        found = lodging._photon_split_stays(SimpleNamespace(_photon_anchor_resource=lookup),
                                            route, self.coords, "refuge", 3, anchors)
        self.assertEqual(sorted(a["route_progress_km"] for a in calls), [4.0, 14.0])
        router = Router()
        result = self.attach(lengths, found, router)
        self.assertEqual(result["logistics"]["nights_walk_confirmed"], 2)
        self.assertEqual(len(router.matrix_calls), 1)
        self.assertAlmostEqual(router.matrix_calls[0][0][1], anchors[0]["lon"])
        self.assertEqual(result["logistics"]["nights"][0]["route_anchor"]["night"], 1)

    def test_middle_gap_does_not_discard_or_renumber_last_night(self):
        lengths = [self.total / 4] * 4
        anchors = lodging._night_anchors(route, self.coords, 4)
        stays = [self.stay(anchors[0], "first"), self.stay(anchors[2], "third")]
        # Discovery can retain a later night even after a missing slot.
        distant = [{**stays[0], "_route_progress_km": 20, "_offroute_km": 0.1},
                   {**stays[1], "_route_progress_km": 60, "_offroute_km": 0.1}]
        fake = SimpleNamespace(_cumulative=lambda coords: [0.0, 80.0])
        chosen = lodging._choose_stays(fake, self.coords, distant, 4, 10)
        self.assertEqual([row["_night"] for row in chosen], [1, 3])
        # Larger real stage spacing keeps those same options away from night 2.
        options = {1: [{**stays[0], "_night": 1, "_anchor_distance_km": 0.1}],
                   2: [], 3: [{**stays[1], "_night": 3, "_anchor_distance_km": 0.1}]}
        evidence = {lodging._connector_key(row): {"validated": True, "return_validated": True,
                    "distance_km": 0.1, "return_distance_km": 0.1}
                    for rows in options.values() for row in rows}
        assigned = lodging._assign_verified_nights(options, evidence, lengths, 15, True)
        self.assertEqual([row["_night"] if row else None for row in assigned], [1, None, 3])

    def test_routed_alternative_beats_nearest_unwalkable_hut(self):
        lengths = [self.total / 2] * 2
        anchor = lodging._night_anchors(route, self.coords, 2)[0]
        closed_access = self.stay(anchor, "blocked", offset=0.001)
        reachable = self.stay(anchor, "reachable", offset=0.003)
        router = Router(unavailable=[Router.key([closed_access["lat"], closed_access["lon"]])])
        result = self.attach(lengths, [closed_access, reachable], router)
        night = result["logistics"]["nights"][0]
        self.assertEqual(night["name"], "reachable")
        self.assertEqual(night["access_mode"], "walk")
        self.assertTrue(night["walking_connector"]["return_validated"])
        self.assertEqual(night["booking_status"], "to_check")
        self.assertFalse(night["transfer_confirmed"])
        self.assertTrue(any(not alt["walking_access_validated"] for alt in result["logistics"]["alternatives"]))
        self.assertEqual(len(router.matrix_calls), 1)
        self.assertLessEqual(len(router.route_calls), 2)

    def test_outbound_only_matrix_is_not_a_confirmed_walking_night(self):
        anchor = lodging._night_anchors(route, self.coords, 2)[0]
        stay = self.stay(anchor, "oneway")
        router = Router(forward_only=[Router.key([stay["lat"], stay["lon"]])])
        result = self.attach([self.total / 2] * 2, [stay], router, strict=True)
        self.assertEqual(result["logistics"]["nights_missing"], 1)
        self.assertEqual(result["logistics"]["nights_walk_confirmed"], 0)
        self.assertEqual(result["logistics"]["nights"][0]["status"], "unresolved")
        self.assertIn("vérifier", result["logistics"]["nights"][0]["action"])

    def test_global_choice_preserves_scarce_later_stay_and_next_day_effort(self):
        def option(name, night):
            return {"name": name, "source_url": f"osm://{name}", "_night": night,
                    "_anchor_distance_km": 0.1}
        options = {1: [option("shared", 1), option("first-only", 1)],
                   2: [option("shared", 2)]}
        evidence = {lodging._connector_key(row): {"validated": True, "return_validated": True,
                    "distance_km": 0.2, "return_distance_km": 0.2}
                    for rows in options.values() for row in rows}
        assigned = lodging._assign_verified_nights(options, evidence, [10, 10, 10], 12, True)
        self.assertEqual([row["name"] for row in assigned], ["first-only", "shared"])
        options = {1: [option("long-return", 1), option("short-return", 1)],
                   2: [option("second", 2)]}
        distances = {"long-return": (0.1, 2.0), "short-return": (0.4, 0.4), "second": (1.5, 0.5)}
        evidence = {lodging._connector_key(row): {"validated": True, "return_validated": True,
                    "distance_km": distances[row["name"]][0], "return_distance_km": distances[row["name"]][1]}
                    for rows in options.values() for row in rows}
        assigned = lodging._assign_verified_nights(options, evidence, [10, 10, 10], 12, False)
        self.assertEqual([row["name"] for row in assigned], ["short-return", "second"])
        self.assertTrue(all(row["_access_mode"] == "walk" for row in assigned))

    def test_same_sourced_campsite_can_cover_two_nights_with_independent_walk_routes(self):
        # Camping at the same hub on consecutive evenings is not a duplicate
        # night. Both end-of-day anchors must have different, valid connectors.
        def option(day):
            return {"name": "Camping partagé",
                    "source_url": "https://www.openstreetmap.org/node/55001",
                    "_night": day, "_anchor_distance_km": 0.2}
        options = {1: [option(1)], 2: [option(2)]}
        assert lodging._connector_key(options[1][0]) != lodging._connector_key(options[2][0])
        connections = {
            lodging._connector_key(options[1][0]): {
                "validated": True, "return_validated": True,
                "distance_km": 0.3, "return_distance_km": 0.35},
            lodging._connector_key(options[2][0]): {
                "validated": True, "return_validated": True,
                "distance_km": 0.4, "return_distance_km": 0.45},
        }
        assigned = lodging._assign_verified_nights(options, connections, [9, 9, 9], 12, True)
        self.assertEqual([x["name"] if x else None for x in assigned],
                         ["Camping partagé", "Camping partagé"])
        self.assertEqual([x["_access_mode"] for x in assigned], ["walk", "walk"])
        self.assertNotEqual(assigned[0]["_connector"]["distance_km"],
                            assigned[1]["_connector"]["distance_km"])

    def test_repeated_campsite_without_second_verified_return_remains_unresolved(self):
        def option(day):
            return {"name": "Refuge unique",
                    "source_url": "https://www.openstreetmap.org/node/55002",
                    "_night": day, "_anchor_distance_km": 0.2}
        options = {1: [option(1)], 2: [option(2)]}
        connections = {
            lodging._connector_key(options[1][0]): {
                "validated": True, "return_validated": True,
                "distance_km": 0.2, "return_distance_km": 0.2},
            lodging._connector_key(options[2][0]): {
                "validated": True, "return_validated": False,
                "distance_km": 0.2, "return_distance_km": 0.2},
        }
        strict = lodging._assign_verified_nights(options, connections, [9, 9, 9], 12, True)
        self.assertIsNotNone(strict[0])
        self.assertIsNone(strict[1])
        flexible = lodging._assign_verified_nights(options, connections, [9, 9, 9], 12, False)
        self.assertIsNotNone(flexible[0])
        self.assertIsNone(flexible[1], "Unverified duplicate must not turn into a transfer")
        # Even with both legs validated, an excessive next-day walking effort
        # cannot be approved solely because the campsite is familiar.
        connections[lodging._connector_key(options[2][0])] = {
            "validated": True, "return_validated": True,
            "distance_km": 3.0, "return_distance_km": 3.0,
        }
        too_far = lodging._assign_verified_nights(options, connections, [11, 11, 11], 12, True)
        self.assertIsNone(too_far[1])

    def test_duplicate_private_unsourced_and_nonfinite_stays_are_not_extra_nights(self):
        anchor = lodging._night_anchors(route, self.coords, 2)[0]
        real = self.stay(anchor, "Same hut", source="https://www.openstreetmap.org/node/10")
        rows = [real, {**real, "source_url": "https://www.openstreetmap.org/way/20"},
                {**real, "name": "Private", "osm_tags": {"access": "private"}},
                {**real, "name": "Made up", "source_url": ""},
                {**real, "name": "Bad coordinates", "lat": float("nan")}]
        projected = lodging._project_stays(route, self.coords, rows, "refuge", 6)
        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["name"], "Same hut")

    def test_provider_and_matrix_size_caps_with_large_pool(self):
        anchors = lodging._night_anchors(route, self.coords, 21)
        calls = []
        def lookup(anchor, *args, **kwargs):
            calls.append(anchor["night"])
            return self.stay(anchor, str(anchor["night"]))
        lodging._photon_split_stays(SimpleNamespace(_photon_anchor_resource=lookup),
                                   route, self.coords, "lodging", 21, anchors)
        self.assertEqual(len(calls), 6)
        options = {a["night"]: [{**self.stay(a, str(a["night"])), "_night": a["night"],
                                "_anchor": a, "_anchor_distance_km": 0.1}] for a in anchors}
        router = Router()
        connectors, meta = lodging._validate_night_options(router, self.legacy, route, self.coords, options)
        self.assertEqual(len(router.matrix_calls), 1)
        self.assertLessEqual(len(router.matrix_calls[0]), 24)
        self.assertLessEqual(len(connectors), 12)
        self.assertEqual(meta["connector_matrix_calls"], 1)

    def test_matrix_fallback_and_driving_cells_do_not_prove_walkability(self):
        anchor = lodging._night_anchors(route, self.coords, 2)[0]
        stay = {**self.stay(anchor, "hut"), "_anchor": anchor, "_night": 1,
                "_anchor_distance_km": 0.1}
        for result in ({"distances": [[0, 1], [1, 0]], "fallback": True},
                       {"distances": [[0, 1], [1, 0]], "fallback": False, "profile": "driving-car"},
                       {"distances": [[0, 1], [None, 0]], "fallback": False}):
            router = SimpleNamespace(get_distance_matrix=lambda points: result)
            self.assertEqual(lodging._matrix_connectors(router, self.coords, [stay]), {})

    def test_provider_timeout_returns_in_budget_without_background_retry(self):
        anchor = lodging._night_anchors(route, self.coords, 2)[0]
        stay = {**self.stay(anchor, "hut"), "_anchor": anchor, "_night": 1,
                "_anchor_distance_km": 0.1}
        router = Router()
        def slow(points, *, timeout_s):
            # Provider transport respects the real remaining timeout, rather
            # than a future returning while an unbounded fake keeps running.
            time.sleep(timeout_s)
            raise TimeoutError("bounded matrix timeout")
        router.get_distance_matrix_bounded = slow
        started = time.monotonic()
        with patch.object(lodging, "_CONNECTOR_BUDGET_SECONDS", 0.025):
            result, meta = lodging._validate_night_options(router, self.legacy, route, self.coords, {1: [stay]})
        self.assertLess(time.monotonic() - started, 0.09)
        self.assertFalse(result)
        self.assertTrue(meta["connector_budget_exhausted"])
        time.sleep(0.13)
        self.assertEqual(len(router.route_calls), 0)

    def test_degraded_guard_keeps_explicit_missing_nights(self):
        result = {"stages": [{"overnight": "Old generic label"} for _ in range(3)], "planner": {}}
        v3 = SimpleNamespace(_parse_intent=lambda data: {"days": 3})
        guard._mark_degraded(result, SimpleNamespace(days=3), v3, "refuge", RuntimeError("provider"))
        self.assertEqual(result["logistics"]["nights_missing"], 2)
        self.assertEqual([n["status"] for n in result["logistics"]["nights"]], ["unresolved", "unresolved"])
        self.assertEqual(result["stages"][0]["overnight_logistics"]["night"], 1)


if __name__ == "__main__":
    unittest.main()
