"""Fail-open guard for TrekBrain v9 route-first lodging.

Accommodation discovery is secondary logistics. A timeout, malformed POI or an
unexpected exception in that layer must never turn an already valid pedestrian
route into TB-INTERNAL-500. If lodging post-processing crashes, rebuild the same
request with lodging removed, keep that validated hiking route, and expose the
lodging problem as a degraded logistics warning.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

_INSTALLED = False


def _fold(value: Any) -> str:
    try:
        from .trekbrain_route_logistics_v9 import _fold as fold
        return fold(value)
    except Exception:
        return str(value or "").strip().casefold()


def _requested_category(v3, data) -> str | None:
    """Use the same category policy as the route-first logistics engine.

    A generic gîte/hotel request also needs a graceful degradation path when
    lodging discovery fails; previously the guard only protected camping/refuges.
    """
    from .trekbrain_route_logistics_v9 import _requested_category as category_for

    try:
        intent = v3._parse_intent(data)
    except Exception:
        return None
    return category_for(intent)


def _route_only(data):
    from .trekbrain_route_logistics_v9 import _clone_route_only
    return _clone_route_only(data)


def _mark_degraded(result: dict[str, Any], data, v3, category: str, exc: Exception) -> dict[str, Any]:
    try:
        intent = v3._parse_intent(data)
    except Exception:
        intent = {}
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    required = max(0, days - 1)
    nights = [{
        "night": night, "status": "unresolved", "access_mode": "to_arrange",
        "reason": "lodging_discovery_failed", "transfer_confirmed": False,
        "note": "La recherche a échoué ; aucune nuitée ni liaison pédestre n'est confirmée.",
        "action": "Relancer la recherche de nuitées et vérifier leur accès avant le départ.",
    } for night in range(1, days)]

    result["logistics"] = {
        "mode": "route-first",
        "category": category,
        "status": "degraded",
        "route_immutable": True,
        "nights_required": required,
        "nights_resolved": 0,
        "nights_walk_confirmed": 0,
        "nights_transfer_required": 0,
        "nights_missing": required,
        "walking_readiness": "missing_nights" if required else "ready_on_foot",
        "ready_without_transfer": required == 0,
        "nights": nights,
        "alternatives": [],
        "error_code": "TB-LOGISTICS-DEGRADED",
        "error_class": exc.__class__.__name__,
        "principle": (
            "Le tracé pédestre a été conservé. La recherche des nuitées a échoué "
            "séparément et pourra être relancée sans recalculer l'itinéraire principal."
        ),
    }

    notes = result.get("advisor_notes")
    if not isinstance(notes, list):
        notes = [str(notes)] if notes else []
        result["advisor_notes"] = notes
    notes.insert(
        0,
        "⚠️ Le parcours pédestre est disponible, mais la recherche des nuitées a rencontré un problème technique. Le trek n'a pas été supprimé pour autant.",
    )

    planner = result.get("planner")
    if not isinstance(planner, dict):
        planner = {}
        result["planner"] = planner
    planner["logistics_mode"] = "route-first"
    planner["logistics_status"] = "degraded"
    planner["lodging_does_not_shape_route"] = True

    stages = result.get("stages")
    if isinstance(stages, list):
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict) or index >= len(stages) - 1:
                continue
            stage["overnight"] = "Nuitée à organiser sans modifier le tracé principal"
            if index < len(nights):
                stage["overnight_logistics"] = nights[index]

    return result


def install_route_logistics_guard(v3) -> None:
    """Wrap the already-installed route-first policy with a safe degradation path."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_build = v3._build

    def build(data, legacy_main):
        category = _requested_category(v3, data)
        if category is None:
            return original_build(data, legacy_main)
        try:
            return original_build(data, legacy_main)
        except HTTPException:
            # Real route/routing errors keep their existing structured diagnostic.
            raise
        except Exception as exc:
            # Lodging is secondary. Rebuild only the pedestrian backbone with the
            # same place/days/distance request and return it instead of a 500.
            route_data = _route_only(data)
            try:
                result = original_build(route_data, legacy_main)
            except HTTPException:
                raise
            except Exception as route_exc:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Le tracé pédestre et la logistique des nuitées ont échoué séparément. "
                        f"Diagnostic technique : TB-ROUTE-RECOVERY ({route_exc.__class__.__name__})."
                    ),
                ) from route_exc
            if not isinstance(result, dict):
                return result
            return _mark_degraded(result, data, v3, category, exc)

    v3._build = build


__all__ = ["install_route_logistics_guard", "_mark_degraded"]
