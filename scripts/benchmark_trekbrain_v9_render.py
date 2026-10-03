"""Opt-in production-environment benchmark for TrekBrain v9.

This script is intentionally not part of normal builds. When
TREKBRAIN_RUN_BENCHMARK=1, render_preflight launches it so route quality and
latency are measured with the same environment variables and external services
as the deployed Render service. It calls the final FastAPI endpoint function
directly, avoiding HTTP authentication while keeping every planner/resource
overlay in the real production order.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from backend import app_v5
from backend.free_planner_v2 import AIPlanRequest


CASES = [
    {
        "id": "sancy",
        "request": AIPlanRequest(
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
        "request": AIPlanRequest(
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
        "request": AIPlanRequest(
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
        "request": AIPlanRequest(
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
    matches = [
        route for route in app_v5.app.routes
        if route.path == "/ai/plan" and "POST" in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one POST /ai/plan endpoint, found {len(matches)}")
    return matches[0].endpoint


def _summary(case_id: str, result: dict[str, Any], elapsed: float) -> dict[str, Any]:
    quality = ((result.get("trekbrain") or {}).get("quality") or {})
    resources = result.get("map_resources") or {}
    logistics = result.get("logistics") or {}
    stages = result.get("stages") or []
    route = result.get("route_preview") or {}
    return {
        "case": case_id,
        "ok": True,
        "elapsed_s": round(elapsed, 2),
        "quality": quality.get("score"),
        "grade": quality.get("grade"),
        "blockers": quality.get("blockers") or [],
        "reasons": quality.get("reasons") or [],
        "route_km": route.get("distance_km") or route.get("distance"),
        "fallback": route.get("fallback"),
        "stage_km": [stage.get("distance_km") for stage in stages if isinstance(stage, dict)],
        "resource_counts": resources.get("counts") or {},
        "nights_resolved": logistics.get("nights_resolved"),
        "nights_required": logistics.get("nights_required"),
        "logistics_status": logistics.get("status"),
    }


def main() -> None:
    endpoint = _plan_endpoint()
    # Deliberately nonexistent user id: learning/personalization falls back to
    # neutral defaults, while route planning itself stays representative.
    user = {"id": 0, "username": "trekbrain-benchmark", "email": "", "is_admin": False}
    rows = []
    for case in CASES:
        started = time.perf_counter()
        try:
            result = endpoint(case["request"], user)
            elapsed = time.perf_counter() - started
            if not isinstance(result, dict):
                raise RuntimeError(f"unexpected result type: {type(result).__name__}")
            row = _summary(case["id"], result, elapsed)
        except HTTPException as exc:
            elapsed = time.perf_counter() - started
            row = {
                "case": case["id"],
                "ok": False,
                "elapsed_s": round(elapsed, 2),
                "http_status": exc.status_code,
                "error": exc.detail,
            }
        except Exception as exc:
            elapsed = time.perf_counter() - started
            row = {
                "case": case["id"],
                "ok": False,
                "elapsed_s": round(elapsed, 2),
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
        print("[TrekBrain benchmark] " + json.dumps(row, ensure_ascii=False), flush=True)

    successful = [row for row in rows if row.get("ok")]
    if successful:
        aggregate = {
            "cases": len(rows),
            "successful": len(successful),
            "avg_elapsed_s": round(
                sum(float(row["elapsed_s"]) for row in successful) / len(successful), 2
            ),
            "max_elapsed_s": max(float(row["elapsed_s"]) for row in successful),
            "avg_quality": round(
                sum(float(row.get("quality") or 0) for row in successful) / len(successful), 1
            ),
        }
    else:
        aggregate = {"cases": len(rows), "successful": 0}
    print("[TrekBrain benchmark summary] " + json.dumps(aggregate, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
