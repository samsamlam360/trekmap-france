"""Offline checks for the production auto-triage safety boundary."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import trekmap_auto_triage as guard


class GuardTests(unittest.TestCase):
    def test_payload_validation(self):
        guard.validate("/health/ready", {"status": "ok"})
        guard.validate("/treks", [])
        guard.validate("/ai/status", {
            "release_channel": "v9-stable",
            "stability_gate": "required", "build_commit": "f" * 40
        }, "f" * 40)
        with self.assertRaises(ValueError):
            guard.validate("/health/ready", {"status": "degraded"})
        with self.assertRaises(ValueError):
            guard.validate("/ai/status", {"release_channel": "v9-stable"}, "f" * 40)
        with self.assertRaises(ValueError):
            guard.validate("/treks", {"treks": []})

    def test_recovery_without_external_calls(self):
        checks = {"attempts": 0}

        def fake_fetch(url, token="", timeout=24):
            if url.endswith("/health/ready"):
                checks["attempts"] += 1
                if checks["attempts"] == 1:
                    raise ValueError("cold start")
                return {"status": "ok"}
            if url.endswith("/treks"):
                return []
            return {"release_channel": "v9-stable",
                    "stability_gate": "required", "build_commit": "f" * 40}

        with patch.object(guard, "fetch", side_effect=fake_fetch):
            self.assertTrue(guard.probe("f" * 40, attempts=4, sleep=lambda _: None))
        self.assertEqual(checks["attempts"], 2)

    def test_no_transient_incident_but_benchmark_still_reported(self):
        self.assertFalse(guard.should_report("TrekMap nightly health", True))
        self.assertFalse(guard.should_report("TrekMap production smoke", True))
        self.assertTrue(guard.should_report(guard.BENCHMARK, True))
        self.assertTrue(guard.should_report("TrekMap nightly health", False))

    def run_event(self, workflow, *, branch="main", conclusion="failure",
                  head_current=True, recovered=True, existing_issues=None):
        sha = "a" * 40
        payload = {"workflow_run": {
            "name": workflow, "conclusion": conclusion, "head_branch": branch,
            "head_sha": sha,
            "html_url": "https://github.com/samsamlam360/trekmap-france/actions/runs/100",
        }}
        with tempfile.TemporaryDirectory() as path:
            event_file = Path(path) / "event.json"
            event_file.write_text(json.dumps(payload), encoding="utf-8")
            environ = {"GITHUB_EVENT_PATH": str(event_file),
                       "GITHUB_REPOSITORY": "samsamlam360/trekmap-france",
                       "GITHUB_TOKEN": "mock-token"}
            def fake_fetch(url, token="", timeout=24):
                if "/commits/main" in url:
                    return {"sha": sha if head_current else "b" * 40}
                if "/issues?state=open" in url:
                    return list(existing_issues or [])
                if "/comments?" in url:
                    return []
                raise AssertionError("unexpected URL: " + url)
            with (patch.dict(os.environ, environ),
                  patch.object(guard, "fetch", side_effect=fake_fetch) as requests,
                  patch.object(guard, "probe", return_value=recovered) as probes,
                  patch.object(guard, "post", return_value={"number": 55}) as posts):
                code = guard.main()
                return code, requests.call_count, probes.call_count, posts.call_args_list

    def test_old_run_never_writes(self):
        code, calls, probes, posts = self.run_event(guard.BENCHMARK, head_current=False)
        self.assertEqual(code, 0)
        self.assertEqual(probes, 0)
        self.assertEqual(posts, [])

    def test_healthy_site_does_not_spawn_issue(self):
        code, _, _, posts = self.run_event("TrekMap nightly health", recovered=True)
        self.assertEqual(code, 0)
        self.assertEqual(posts, [])

    def test_benchmark_failure_creates_issue_even_if_site_healthy(self):
        code, _, _, posts = self.run_event(guard.BENCHMARK, recovered=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].args[1]["title"], guard.TITLE_PREFIX + guard.BENCHMARK)

    def test_existing_incident_is_reused(self):
        issue = {"title": guard.TITLE_PREFIX + guard.BENCHMARK, "number": 12}
        code, _, _, posts = self.run_event(guard.BENCHMARK, existing_issues=[issue])
        self.assertEqual(code, 0)
        self.assertEqual(len(posts), 1)
        self.assertIn("/issues/12/comments", posts[0].args[0])

    def test_untrusted_branch_does_nothing(self):
        code, calls, probes, posts = self.run_event(guard.BENCHMARK, branch="patch")
        self.assertEqual(code, 0)
        self.assertEqual((calls, probes, len(posts)), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
