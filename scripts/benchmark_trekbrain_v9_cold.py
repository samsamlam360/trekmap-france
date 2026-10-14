"""Manual first-visit audit with real existing ORS credentials and finite budgets.

Every case starts in a fresh process, with an unreachable database and the
persistent OSM cache disabled. Provider caches remain outside our control.
No account, key, paid service or production configuration is created or changed.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("huelgoat", "Huelgoat, Finistère", 2, 16),
    ("bagnoles", "Bagnoles-de-l'Orne, Orne", 2, 16),
    ("gerardmer", "Gérardmer, Vosges", 2, 16),
    ("saint-antonin", "Saint-Antonin-Noble-Val, Tarn-et-Garonne", 2, 16),
]
PREFIX = "[TrekBrain cold] "
CASE_TIMEOUT_SECONDS = 90
SUITE_TIMEOUT_SECONDS = 400
MIN_INTERVAL_SECONDS = 20


def isolated_environment():
    env = dict(os.environ)
    env.update(
        DATABASE_URL="postgresql://benchmark:benchmark@127.0.0.1:1/isolated",
        DB_CONNECT_TIMEOUT="1", TREKBRAIN_OSM_CACHE="0",
        TREKBRAIN_FREE_MODE="1", TREKBRAIN_VERSION="v9", TREKMAP_ENV="development",
        PYTHONUNBUFFERED="1",
    )
    return env


def isolation_valid(row):
    cache = row.get("osm_cache")
    if not isinstance(cache, dict):
        return False
    return cache.get("status") == "not_attempted" and cache.get("count") == 0


def child(index):
    # Isolation must be active before importing any app module, even when the
    # child is invoked directly. Fresh processes discard all in-memory caches.
    os.environ.update(isolated_environment())
    sys.path.insert(0, str(ROOT))
    from benchmark_trekbrain_v9_render import _plan_endpoint, _summary, configuration_error
    from benchmark_trekbrain_v9_production import failure_row
    error = configuration_error()
    name, region, days, daily = CASES[index]
    if error:
        row = failure_row(name, error, status="configuration_error")
    else:
        started = time.perf_counter()
        try:
            from backend.free_planner_v2 import AIPlanRequest
            from fastapi import HTTPException
            request = AIPlanRequest(
                prompt=f"Boucle à pied de {days} jours autour de {region}, environ {daily} km par jour, avec gîte, eau et ravitaillement.",
                region=region, days=days, daily_km=daily, route_type="Boucle",
                require_transit=False, require_food=True, require_water=True,
                require_accommodation=True,
            )
            result = _plan_endpoint()(request, {"id": 0, "username": "cold-audit", "is_admin": False})
            if not isinstance(result, dict):
                raise TypeError("unexpected planner result")
            row = _summary(name, result, time.perf_counter() - started, request)
            row["nights"] = (result.get("logistics") or {}).get("nights") or []
            row["coverage"] = (result.get("map_resources") or {}).get("coverage") or {}
            row["osm_cache"] = ((result.get("planner") or {}).get("resource_overlay") or {}).get("osm_cache")
            row["cache_isolation_valid"] = isolation_valid(row)
            if not row["cache_isolation_valid"]:
                row.update(ok=False, status="isolation_error", preparation_ok=False)
                row["hard_failures"].append("Persistent cache isolation could not be verified")
        except Exception as exc:
            http_status = getattr(exc, "status_code", None)
            row = failure_row(name, f"Planner refusal HTTP {http_status}" if http_status else type(exc).__name__, time.perf_counter() - started, http_status=http_status)
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                row["diagnostic"] = detail.get("diagnostic")
    row.update(isolated_process=True, persistent_cache_disabled=True, database_isolated=True)
    print(PREFIX + json.dumps(row, ensure_ascii=False), flush=True)


def run_cases():
    from benchmark_trekbrain_v9_production import failure_row
    rows = []
    last_started = None
    deadline = time.monotonic() + SUITE_TIMEOUT_SECONDS
    for index, case in enumerate(CASES):
        if last_started is not None:
            time.sleep(max(0.0, MIN_INTERVAL_SECONDS - (time.monotonic() - last_started)))
        last_started = time.monotonic()
        remaining = deadline - last_started
        if remaining <= 0:
            row = failure_row(case[0], "suite_budget_exhausted", status="runtime_error")
        else:
            try:
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--case", str(index)],
                    env=isolated_environment(), cwd=ROOT, capture_output=True, text=True,
                    timeout=min(CASE_TIMEOUT_SECONDS, remaining),
                )
                records = [line[len(PREFIX):] for line in proc.stdout.splitlines() if line.startswith(PREFIX)]
                if proc.returncode or len(records) != 1:
                    row = failure_row(case[0], "child_failed", status="runtime_error")
                    row["returncode"] = proc.returncode
                else:
                    row = json.loads(records[0])
                    if not isinstance(row, dict) or row.get("id") != case[0]:
                        row = failure_row(case[0], "invalid_child_record", status="runtime_error")
            except subprocess.TimeoutExpired:
                row = failure_row(case[0], "case_timeout_90s", time.monotonic() - last_started, status="runtime_error")
            except (ValueError, OSError):
                row = failure_row(case[0], "child_record_unavailable", status="runtime_error")
        rows.append(row)
        print(PREFIX + json.dumps(row, ensure_ascii=False), flush=True)
    return rows


def main(*, check_config=False):
    from benchmark_trekbrain_v9_render import configuration_error, save_reports
    from benchmark_trekbrain_v9_production import failure_row
    error = configuration_error()
    if error:
        rows = [failure_row("configuration", error, status="configuration_error")]
        print("[TrekBrain cold summary] " + json.dumps(save_reports(rows, suite="cold", error=error), ensure_ascii=False), flush=True)
        raise SystemExit(2)
    if check_config:
        print("[TrekBrain cold] Existing ORS credential configured; live audit not started.", flush=True)
        return
    rows = run_cases()
    aggregate = save_reports(rows, suite="cold")
    aggregate.update(
        persistent_cache_disabled=True, database_isolated=True,
        process_isolation="fresh_child_per_case", provider_caches_controlled=False,
        case_timeout_s=CASE_TIMEOUT_SECONDS, suite_timeout_s=SUITE_TIMEOUT_SECONDS,
        minimum_interval_s=MIN_INTERVAL_SECONDS,
    )
    output = Path(os.getenv("TREKBRAIN_BENCHMARK_OUT", "benchmark-results/cold"))
    (output / "trekbrain-cold-benchmark.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[TrekBrain cold summary] " + json.dumps(aggregate, ensure_ascii=False), flush=True)
    # An HTTP refusal, missing mandatory need or missing isolation telemetry is
    # a real unsuccessful case, even when the child process itself exits cleanly.
    if any(row.get("ok") is not True or row.get("cache_isolation_valid") is not True for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        child(int(sys.argv[2]))
    else:
        main(check_config=sys.argv[1:] == ["--check-config"])
