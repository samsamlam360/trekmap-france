"""Opt-in production-environment benchmark for TrekBrain v9.

This script is intentionally not part of normal builds. Run manually after
deployment; Render builds never launch this live audit.
Route quality and latency use the same environment variables and external
services as the deployed Render service. It calls the final FastAPI endpoint function
directly, avoiding HTTP authentication while keeping every planner/resource
overlay in the real production order.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES_DATA = [
    {
        "id": "sancy",
        "request": dict(
            prompt=(
                "Je veux une boucle de randonnée de 3 jours dans le massif du Sancy, "
                "environ 18 km par jour, avec des points d'eau, du ravitaillement "
                "et un hébergement chaque soir."
            ),
            region="Massif du Sancy",
            days=3,
            daily_km=18,
            route_type="Boucle",
            require_transit=True,
            require_water=True,
            require_accommodation=True,
            require_food=True,
        ),
    },
    {
        "id": "tours-chinon",
        "request": dict(
            prompt=(
                "Je veux faire un trek de Tours à Chinon en 3 jours, environ 22 km "
                "par jour. Ce n'est pas une boucle. Je veux suivre au maximum les "
                "vrais chemins de randonnée, avec eau, ravitaillement, hébergement "
                "et transports utiles."
            ),
            region="Tours",
            days=3,
            daily_km=22,
            route_type="Traversée",
            require_transit=True,
            require_water=True,
            require_accommodation=True,
            require_food=True,
        ),
    },
    {
        "id": "vercors",
        "request": dict(
            prompt=(
                "Je veux une itinérance de 3 jours dans le Vercors, environ 20 km "
                "par jour, en privilégiant les vrais sentiers, avec refuge ou gîte "
                "chaque soir, points d'eau et ravitaillement."
            ),
            region="Vercors",
            days=3,
            daily_km=20,
            route_type="Itinérance",
            require_transit=True,
            require_water=True,
            require_accommodation=True,
            require_food=True,
        ),
    },
    {
        "id": "belle-ile",
        "request": dict(
            prompt=(
                "Je veux faire le tour de Belle-Île-en-Mer en boucle sur 5 jours, "
                "environ 18 km par jour, avec un camping pour dormir chaque soir. "
                "Je veux suivre au maximum le GR 340, avec points d'eau et "
                "ravitaillement utiles sans déformer le parcours principal."
            ),
            region="Belle-Île-en-Mer",
            days=5,
            daily_km=18,
            route_type="Boucle",
            require_transit=True,
            require_water=True,
            require_accommodation=True,
            require_food=True,
        ),
    },
]


def _plan_endpoint():
    from backend import app_v5
    matches = [
        route for route in app_v5.app.routes
        if route.path == "/ai/plan" and "POST" in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one POST /ai/plan endpoint, found {len(matches)}")
    return matches[0].endpoint


def _summary(case_id: str, result: dict[str, Any], elapsed: float, request=None) -> dict[str, Any]:
    from benchmark_trekbrain_v9_production import evaluate, fold
    payload = request.model_dump() if request is not None and hasattr(request, "model_dump") else request or {}
    route_type = fold(payload.get("route_type") or result.get("route_type"))
    case = {
        "id": case_id,
        "days": int(payload.get("days") or len(result.get("stages") or []) or 1),
        "daily_km": float(payload.get("daily_km") or 16),
        "expect_type": "boucle" if "boucle" in route_type else "traversee" if "traversee" in route_type else "itinerance",
        "expect_close": "boucle" in route_type,
        **{name: bool(payload.get(name)) for name in (
            "require_transit", "require_water", "require_accommodation", "require_food",
        )},
    }
    row = evaluate(case, result, elapsed, {})
    row["case"] = case_id
    row["core_total_ms"] = row.get("planner_ms")
    return row


def configuration_error():
    key = os.getenv("ORS_API_KEY", "").strip()
    if not key or key.casefold() in {"ci-placeholder", "placeholder", "dummy", "test"}:
        return "ORS_API_KEY missing or placeholder: configure an existing routing credential before live benchmarks"
    return None


def save_reports(rows, *, suite="render", error=None):
    import benchmark_trekbrain_v9_production as core
    core.OUT_DIR = Path(os.getenv("TREKBRAIN_BENCHMARK_OUT", f"benchmark-results/{suite}"))
    core.OUT_DIR.mkdir(parents=True, exist_ok=True)
    core.write_reports({"suite": suite, "error": error, "scenario_count": len(CASES_DATA)}, rows)
    (core.OUT_DIR / f"trekbrain-{suite}-benchmark.md").write_text(
        (core.OUT_DIR / "trekbrain-production-benchmark.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    aggregate = {
        "cases": len(rows),
        "structure_valid": sum(row.get("structure_ok") is True for row in rows),
        "preparation_complete": sum(row.get("preparation_ok") is True for row in rows),
        "successful": sum(row.get("ok") is True for row in rows),
        "refused": sum(row.get("status") == "refused" for row in rows),
        "incomplete": sum(row.get("status") == "incomplete" for row in rows),
        "configuration_errors": sum(row.get("status") == "configuration_error" for row in rows),
        "runtime_errors": sum(row.get("status") == "runtime_error" for row in rows),
        "isolation_errors": sum(row.get("status") == "isolation_error" for row in rows),
        "rows": rows,
    }
    (core.OUT_DIR / f"trekbrain-{suite}-benchmark.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return aggregate


PREFIX = "[TrekBrain benchmark] "
CASE_TIMEOUT_SECONDS = 90
SUITE_TIMEOUT_SECONDS = 400


def _run_case(index):
    from benchmark_trekbrain_v9_production import failure_row
    case = CASES_DATA[index]
    started = time.perf_counter()
    try:
        from backend.free_planner_v2 import AIPlanRequest
        request = AIPlanRequest(**case["request"])
        result = _plan_endpoint()(request, {"id": 0, "username": "trekbrain-benchmark", "email": "", "is_admin": False})
        if not isinstance(result, dict):
            raise RuntimeError("unexpected planner result type")
        return _summary(case["id"], result, time.perf_counter() - started, request)
    except Exception as exc:
        http_status = getattr(exc, "status_code", None)
        row = failure_row(case["id"], f"Planner refusal HTTP {http_status}" if http_status else type(exc).__name__, time.perf_counter() - started, http_status=http_status)
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            row["diagnostic"] = detail.get("diagnostic")
        return row


def main() -> None:
    from benchmark_trekbrain_v9_production import failure_row
    error = configuration_error()
    if error:
        rows = [failure_row("configuration", error, status="configuration_error")]
        print("[TrekBrain benchmark summary] " + json.dumps(save_reports(rows, error=error), ensure_ascii=False), flush=True)
        raise SystemExit(2)

    rows = []
    last_started = None
    deadline = time.monotonic() + SUITE_TIMEOUT_SECONDS
    for index, case in enumerate(CASES_DATA):
        if last_started is not None:
            time.sleep(max(0.0, 20.0 - (time.monotonic() - last_started)))
        last_started = time.monotonic()
        remaining = deadline - last_started
        if remaining <= 0:
            row = failure_row(case["id"], "suite_budget_exhausted", status="runtime_error")
        else:
            try:
                proc = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--case", str(index)],
                    env=dict(os.environ), cwd=ROOT, capture_output=True, text=True,
                    timeout=min(CASE_TIMEOUT_SECONDS, remaining),
                )
                records = [line[len(PREFIX):] for line in proc.stdout.splitlines() if line.startswith(PREFIX)]
                row = json.loads(records[0]) if not proc.returncode and len(records) == 1 else None
                if not isinstance(row, dict) or row.get("id") != case["id"]:
                    row = failure_row(case["id"], "child_failed", status="runtime_error")
                    row["returncode"] = proc.returncode
            except subprocess.TimeoutExpired:
                row = failure_row(case["id"], "case_timeout_90s", time.monotonic() - last_started, status="runtime_error")
            except (ValueError, OSError):
                row = failure_row(case["id"], "child_record_unavailable", status="runtime_error")
        rows.append(row)
        print(PREFIX + json.dumps(row, ensure_ascii=False), flush=True)
    aggregate = save_reports(rows)
    print("[TrekBrain benchmark summary] " + json.dumps(aggregate, ensure_ascii=False), flush=True)
    if any(row.get("ok") is not True for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        error = configuration_error()
        if error:
            from benchmark_trekbrain_v9_production import failure_row
            row = failure_row("configuration", error, status="configuration_error")
        else:
            row = _run_case(int(sys.argv[2]))
        print(PREFIX + json.dumps(row, ensure_ascii=False), flush=True)
    else:
        main()
