"""Public request-reconciliation overlay for TrekBrain v9.

It sits outside the normal planner endpoints so stale mobile form values are
resolved before clarification, island filtering, Web research and routing start.
"""
from __future__ import annotations

from fastapi import Body, Depends

from . import smart_planner_v7 as v7
from .trekbrain_request_v9 import reconcile_request


def _effective_payload(data):
    resolved, meta = reconcile_request(data)
    # Reuse the same parser as TrekBrain v9 for non-geographic fields. Import
    # lazily to avoid a module cycle during application startup.
    from .smart_planner_v9 import _effective_request

    effective = _effective_request(resolved)
    meta = dict(meta)
    meta.update({
        "effective_days": int(effective.days),
        "effective_daily_km": float(effective.daily_km),
        "effective_difficulty": str(effective.difficulty),
        "effective_route_type": str(effective.route_type),
        "effective_transit": bool(effective.require_transit),
    })
    return effective, meta


def _public_effective(data):
    return {
        "region": str(data.region or ""),
        "days": int(data.days),
        "daily_km": float(data.daily_km),
        "difficulty": str(data.difficulty),
        "route_type": str(data.route_type),
        "require_transit": bool(data.require_transit),
        "require_water": bool(data.require_water),
        "require_accommodation": bool(data.require_accommodation),
        "require_food": bool(data.require_food),
    }


def _wrap_post(app, path: str, legacy_main, *, add_note: bool):
    original = next(
        (
            r for r in app.router.routes
            if getattr(r, "path", None) == path and "POST" in getattr(r, "methods", set())
        ),
        None,
    )
    if original is None:
        raise RuntimeError(f"Route {path} introuvable pour la réconciliation TrekBrain.")
    endpoint = original.endpoint
    app.router.routes = [r for r in app.router.routes if r is not original]

    @app.post(path)
    def reconciled(
        data: v7.v5.v3.AIPlanRequest = Body(...),
        user=Depends(legacy_main.current_user),
    ):
        effective, meta = _effective_payload(data)
        result = endpoint(effective, user)
        if not isinstance(result, dict):
            return result
        result["effective_request"] = _public_effective(effective)
        result["request_resolution"] = meta
        if add_note and meta.get("region_overridden"):
            notes = result.setdefault("advisor_notes", [])
            note = (
                f"🧭 J’ai remplacé la région du formulaire « {meta.get('original_region') or 'vide'} » "
                f"par « {meta.get('effective_region')} », car ta demande écrite indique clairement ce lieu."
            )
            if note not in notes:
                notes.insert(0, note)
        return result


def install_request_overlay(app, legacy_main):
    # Install after the geographic-safety overlay. This makes reconciliation the
    # outermost layer, so even island bounds see the corrected region.
    _wrap_post(app, "/ai/clarify", legacy_main, add_note=False)
    _wrap_post(app, "/ai/plan", legacy_main, add_note=True)
