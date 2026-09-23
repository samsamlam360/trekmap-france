"""Explicit TrekBrain v9 planning pipeline.

This module replaces three nested ``v3._build`` wrappers with one orchestrator:

    understand -> build pedestrian route -> attach lodging logistics -> finalize

The geographic engines underneath are intentionally unchanged. The point of this
refactor is not to invent another planner. It is to make ownership explicit so a
camping fix cannot silently change Belle-Île routing, and a Belle-Île fix cannot
silently bypass the generic non-GR planner.

Specialised modules remain reusable helpers:
- ``trekbrain_belle_ile_canonical_v9`` owns the canonical GR 340 route builder;
- ``trekbrain_route_logistics_v9`` owns lodging discovery/attachment;
- ``trekbrain_route_logistics_guard_v9`` owns degraded-logistics annotations.

Only this module mutates ``v3._build`` for those three responsibilities in the
production installer chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import HTTPException

_INSTALLED = False
PIPELINE_VERSION = "v9-explicit-1"


@dataclass
class PlanningState:
    data: Any
    route_data: Any
    intent: dict[str, Any]
    category: str | None
    phases: list[str] = field(default_factory=list)
    route_result: dict[str, Any] | None = None


def _category(logistics_module, intent: dict[str, Any]) -> str | None:
    try:
        return logistics_module._requested_category(intent)
    except Exception:
        return None


def _route_request(logistics_module, data, category: str | None):
    if category is None:
        return data
    return logistics_module._clone_route_only(data)


def _build_backbone(
    state: PlanningState,
    legacy_main,
    *,
    base_build: Callable,
    v3,
    canonical,
    gr,
    rescue,
    roundtrip,
    stitch,
    ors,
    belle,
):
    """Build exactly one pedestrian backbone, canonical when applicable."""
    state.phases.append("route")

    # The canonical builder returns None for non-Belle-Île/non-loop requests.
    # This is a dispatcher, not another wrapper around the generic planner.
    canonical_result = canonical._build_canonical(
        state.route_data,
        legacy_main,
        v3,
        gr,
        rescue,
        roundtrip,
        stitch,
        ors,
        belle,
    )
    if canonical_result is not None:
        state.phases.append("route:canonical-gr340")
        return canonical_result

    state.phases.append("route:generic")
    return base_build(state.route_data, legacy_main)


def _mark_pipeline(result: dict[str, Any], state: PlanningState) -> dict[str, Any]:
    planner = result.get("planner")
    if not isinstance(planner, dict):
        planner = {}
        result["planner"] = planner
    planner["pipeline_version"] = PIPELINE_VERSION
    planner["pipeline_phases"] = list(state.phases)
    planner["single_orchestrator"] = True
    return result


def install_planning_pipeline(
    v3,
    gr,
    rescue,
    roundtrip,
    stitch,
    ors,
    belle,
    stay_rescue,
    logistics_module,
    logistics_guard,
    canonical_module,
) -> None:
    """Install one route/logistics orchestrator in place of three nested wrappers."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # Capture the already-installed generic geographic planner stack. Nothing in
    # this module patches GR discovery, ORS, path networks or distance tolerance.
    base_build = v3._build

    def build(data, legacy_main):
        try:
            intent = v3._parse_intent(data)
        except Exception:
            # Preserve the underlying planner's existing structured diagnostics.
            return base_build(data, legacy_main)

        category = _category(logistics_module, intent)
        route_data = _route_request(logistics_module, data, category)
        state = PlanningState(
            data=data,
            route_data=route_data,
            intent=dict(intent or {}),
            category=category,
            phases=["understand"],
        )

        try:
            result = _build_backbone(
                state,
                legacy_main,
                base_build=base_build,
                v3=v3,
                canonical=canonical_module,
                gr=gr,
                rescue=rescue,
                roundtrip=roundtrip,
                stitch=stitch,
                ors=ors,
                belle=belle,
            )
        except HTTPException:
            raise
        except Exception as exc:
            # Match the previous lodging guard's useful behaviour: only a
            # lodging-request path receives one bounded route retry. Requests
            # without lodging keep the old exception semantics.
            if category is None:
                raise
            state.phases.append("route:retry")
            try:
                result = _build_backbone(
                    state,
                    legacy_main,
                    base_build=base_build,
                    v3=v3,
                    canonical=canonical_module,
                    gr=gr,
                    rescue=rescue,
                    roundtrip=roundtrip,
                    stitch=stitch,
                    ors=ors,
                    belle=belle,
                )
            except HTTPException:
                raise
            except Exception as route_exc:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Le tracé pédestre a échoué avant la logistique des nuitées. "
                        f"Diagnostic technique : TB-ROUTE-RECOVERY ({route_exc.__class__.__name__})."
                    ),
                ) from route_exc

        if not isinstance(result, dict):
            return result
        state.route_result = result

        # The route is now authoritative. Lodging may annotate it, never rebuild
        # or reshape it. This was the important boundary missing from the old
        # wrapper stack.
        if category is not None:
            state.phases.append("logistics")
            try:
                result = logistics_module._attach_logistics(
                    result,
                    data,
                    legacy_main,
                    v3,
                    roundtrip,
                    stay_rescue,
                    ors,
                    intent,
                    category,
                )
            except HTTPException:
                raise
            except Exception as exc:
                state.phases.append("logistics:degraded")
                # We already possess the valid route, so unlike the previous guard
                # there is no reason to calculate it a second time.
                result = logistics_guard._mark_degraded(
                    result,
                    data,
                    v3,
                    category,
                    exc,
                )

        state.phases.append("finalize")
        return _mark_pipeline(result, state)

    v3._build = build


__all__ = [
    "PIPELINE_VERSION",
    "PlanningState",
    "install_planning_pipeline",
    "_build_backbone",
]
