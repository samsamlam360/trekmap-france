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
import math
import time
import re
import unicodedata
from typing import Any, Callable

from fastapi import HTTPException

from . import trekbrain_perf_profile_v9 as perf

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



def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _relation_candidate_loop_allowed(intent: dict[str, Any]) -> bool:
    """Try real hiking-route evidence before generic routing for multi-day loops.

    This is deliberately broad and destination-agnostic. It does not know TMB,
    GR340, Crozon or any other route name. Long loops are exactly where asking a
    generic router to invent the whole trek is weakest, while an existing hiking
    relation is strong evidence when its geometry, length and start proximity fit.
    """
    if _fold(intent.get("route_type") or "") != "boucle":
        return False
    try:
        days = int(intent.get("days") or 1)
        total = float(intent.get("total_target") or 0)
    except (TypeError, ValueError):
        return False
    if days < 2 or days > 12 or total < 24.0 or total > 260.0:
        return False
    if intent.get("start_query") or intent.get("end_query") or intent.get("via_query"):
        return False
    return True


def _fast_generic_loop_allowed(intent: dict[str, Any]) -> bool:
    """Use the stable ORS loop engine directly for simple short loops."""
    if _fold(intent.get("route_type") or "") != "boucle":
        return False
    try:
        days = int(intent.get("days") or 1)
        total = float(intent.get("total_target") or 0)
    except (TypeError, ValueError):
        return False
    if days < 2 or days > 3 or total <= 0 or total > 65.0:
        return False
    if intent.get("start_query") or intent.get("end_query") or intent.get("via_query"):
        return False
    if intent.get("max_dplus_day"):
        return False
    if intent.get("avoid"):
        return False
    raw = _fold(intent.get("raw") or "")
    if re.search(r"\b(?:gr\s*\d+|grp\b|pr\s*\d+)\b", raw):
        return False
    return True


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

    # Candidate-first planning: for any compatible multi-day loop, let the
    # relation-aware round-trip stack inspect real hiking evidence before the
    # legacy planner asks ORS to invent a circuit. The patched _best_roundtrip
    # checks relations first; if no relation fits, long routes fail cheaply at
    # the ORS safety cap and continue to the generic planner below.
    if _relation_candidate_loop_allowed(state.intent):
        state.phases.append("route:candidate-relations")
        try:
            return roundtrip._build_roundtrip(state.route_data, legacy_main, v3)
        except HTTPException as exc:
            state.phases.append("route:candidate-miss")
            detail = str(getattr(exc, "detail", exc) or "")
            print(
                "[TrekBrain v9][candidate-miss] "
                f"status={getattr(exc, 'status_code', 422)} "
                f"days={state.intent.get('days')} "
                f"target={state.intent.get('total_target')} "
                f"detail={detail[:700]}",
                flush=True,
            )

    elif _fast_generic_loop_allowed(state.intent):
        state.phases.append("route:generic-fast-ors")
        try:
            return roundtrip._build_roundtrip(state.route_data, legacy_main, v3)
        except HTTPException:
            state.phases.append("route:generic-fast-miss")

    state.phases.append("route:generic")
    return base_build(state.route_data, legacy_main)


def _haversine(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(
        math.radians,
        (float(a[0]), float(a[1]), float(b[0]), float(b[1])),
    )
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def _rebalance_stage_count(result: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    """Split one validated route into the exact requested number of hiking days.

    The route geometry is never redrawn here. We only place stage boundaries on
    the existing pedestrian polyline at equal cumulative progress. This is the
    safe recovery for point-to-point routes where POI discovery found too few
    suitable overnight boundary objects even though the route itself is valid.
    """
    requested = max(1, int((intent or {}).get("days") or 1))
    stages = result.get("stages") or []
    if len(stages) == requested:
        return result

    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    if route.get("fallback") is not False or len(coords) < requested + 1:
        return result

    clean = []
    for point in coords:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            if not clean or [lat, lon] != clean[-1]:
                clean.append([lat, lon])
    if len(clean) < requested + 1:
        return result

    cumulative = [0.0]
    for a, b in zip(clean, clean[1:]):
        cumulative.append(cumulative[-1] + _haversine(a, b))
    geometric_total = cumulative[-1]
    if geometric_total <= 0:
        return result

    indices = [0]
    floor = 1
    for day in range(1, requested):
        target = geometric_total * day / requested
        if floor >= len(clean) - 1:
            return result
        idx = min(range(floor, len(clean) - 1), key=lambda i: abs(cumulative[i] - target))
        indices.append(idx)
        floor = idx + 1
    indices.append(len(clean) - 1)

    try:
        routed_total = float(route.get("distance_km") or route.get("distance") or geometric_total)
    except (TypeError, ValueError):
        routed_total = geometric_total
    if not math.isfinite(routed_total) or routed_total <= 0:
        routed_total = geometric_total
    scale = routed_total / geometric_total

    accommodations = [x for x in (result.get("accommodations") or []) if isinstance(x, dict)]
    original = [x for x in stages if isinstance(x, dict)]
    rebuilt = []
    for day in range(requested):
        a_idx, b_idx = indices[day], indices[day + 1]
        a_coord, b_coord = clean[a_idx], clean[b_idx]
        distance = max(0.1, (cumulative[b_idx] - cumulative[a_idx]) * scale)
        template = original[min(day, len(original) - 1)] if original else {}

        from_name = (
            str((result.get("start") or {}).get("name") or "Départ")
            if day == 0 else f"Repère jour {day}"
        )
        to_name = (
            str((result.get("end") or {}).get("name") or "Arrivée")
            if day == requested - 1 else f"Repère jour {day + 1}"
        )
        overnight = "Fin du trek"
        if day < requested - 1:
            overnight = "Nuitée à confirmer près du repère d'étape"
            if accommodations:
                nearest = min(
                    accommodations,
                    key=lambda stay: _haversine(
                        b_coord,
                        [float(stay.get("lat") or 0), float(stay.get("lon") or 0)],
                    ),
                )
                try:
                    if _haversine(b_coord, [float(nearest["lat"]), float(nearest["lon"])]) <= 6.2:
                        overnight = str(nearest.get("name") or overnight)
                except (KeyError, TypeError, ValueError):
                    pass

        rebuilt.append({
            **template,
            "day": day + 1,
            "name": f"Jour {day + 1}",
            "title": f"{from_name} → {to_name}",
            "from_name": from_name,
            "to_name": to_name,
            "distance_km": round(distance, 1),
            "overnight": overnight,
            "stage_anchor": {"lat": b_coord[0], "lon": b_coord[1]} if day < requested - 1 else None,
        })

    result["stages"] = rebuilt
    result["duration_days"] = requested
    planner = result.setdefault("planner", {})
    if isinstance(planner, dict):
        planner["stage_rebalanced"] = True
        planner["stage_rebalanced_from"] = len(stages)
    notes = result.setdefault("advisor_notes", [])
    note = (
        f"🧭 Les {requested} journées ont été rééquilibrées le long du tracé pédestre "
        "validé afin de respecter la durée demandée sans modifier la géométrie."
    )
    if isinstance(notes, list) and note not in notes:
        notes.append(note)
    return result


def _preload_canonical_stays(
    result: dict[str, Any],
    state: PlanningState,
    *,
    canonical,
    roundtrip,
    stay_rescue,
) -> int:
    """Restore Belle-Île's dedicated stay discovery after route-only planning.

    The explicit v9 pipeline deliberately removes lodging from the request before
    building the pedestrian backbone.  That keeps campings from shaping GR 340,
    but it must not discard the canonical planner's specialised island-wide stay
    discovery.  Preload real overnight candidates *after* the route is fixed;
    route-first logistics will still validate connectors and remains the only
    layer allowed to annotate nights.
    """
    category = state.category
    if not result.get("canonical_route") or category not in {"camping", "refuge"}:
        return 0

    try:
        days = max(1, int(state.intent.get("days") or 1))
    except (TypeError, ValueError):
        days = 1
    needed = max(0, days - 1)
    if needed <= 0:
        return 0

    existing = [
        dict(row)
        for row in (result.get("accommodations") or [])
        if isinstance(row, dict)
        and str(row.get("category") or "").casefold() == category
    ]
    if len(existing) >= needed:
        return len(existing)

    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    if len(coords) < 3:
        return 0

    start = dict(result.get("start") or {})
    if "lat" not in start or "lon" not in start:
        try:
            start = {
                "name": "Départ GR 340",
                "lat": float(coords[0][0]),
                "lon": float(coords[0][1]),
                "category": "trail",
            }
        except (TypeError, ValueError, IndexError):
            return 0

    try:
        daily_target = float(state.intent.get("daily_target") or 18.0)
    except (TypeError, ValueError):
        daily_target = 18.0
    try:
        daily_min = float(state.intent.get("daily_min") or daily_target * 0.75)
    except (TypeError, ValueError):
        daily_min = daily_target * 0.75
    try:
        daily_max = float(state.intent.get("daily_max") or daily_target * 1.25)
    except (TypeError, ValueError):
        daily_max = daily_target * 1.25

    discovered = list(existing)
    chosen = []
    projected = []
    provider_rows = {}
    radius = 30.0
    providers = (
        ("overpass", getattr(stay_rescue, "_direct_stays", None)),
        ("photon", getattr(stay_rescue, "_photon_stays", None)),
        ("nominatim", getattr(stay_rescue, "_nominatim_stays", None)),
    )

    for provider_name, provider in providers:
        if not callable(provider):
            continue
        started = time.perf_counter()
        rows = []
        outcome = "ok"
        try:
            rows = list(provider(start, category, radius) or [])
        except Exception:
            outcome = "error"
            rows = []
        finally:
            perf.record(
                f"logistics.canonical_{provider_name}",
                (time.perf_counter() - started) * 1000,
                category=category,
                outcome=outcome,
            )
        provider_rows[provider_name] = len(rows)
        discovered.extend(rows)
        try:
            projected = canonical._project_stays(
                roundtrip, coords, discovered, category
            )
            chosen = canonical._choose_ordered_stays(
                roundtrip,
                coords,
                projected,
                days,
                daily_target,
                daily_min,
                daily_max,
            )
        except Exception:
            projected, chosen = [], []
        if len(chosen) >= needed:
            break

    diagnostics = {
        "needed": needed,
        "discovered": len(projected),
        "chosen": len(chosen),
        "max_offroute_km": getattr(canonical, "_MAX_STAY_OFFROUTE_KM", 5.0),
        "providers": provider_rows,
        "source": "canonical-preload",
    }
    result["stay_search"] = diagnostics

    planner = result.setdefault("planner", {})
    if isinstance(planner, dict):
        planner["canonical_stays_preloaded"] = len(chosen)
        planner["canonical_stay_search"] = diagnostics

    if chosen:
        result["accommodations"] = [dict(row) for row in chosen]
    return len(chosen)


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
            result = perf.call(
                "phase.route",
                _build_backbone,
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
                result = perf.call(
                "phase.route",
                _build_backbone,
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

        if category is not None:
            preloaded = _preload_canonical_stays(
                result,
                state,
                canonical=canonical_module,
                roundtrip=roundtrip,
                stay_rescue=stay_rescue,
            )
            if preloaded:
                state.phases.append("logistics:canonical-preload")

        # The route is now authoritative. Lodging may annotate it, never rebuild
        # or reshape it. This was the important boundary missing from the old
        # wrapper stack.
        if category is not None:
            state.phases.append("logistics")
            try:
                result = perf.call(
                    "phase.logistics",
                    logistics_module._attach_logistics,
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
                print(
                    "[TrekBrain v9][logistics-degraded] "
                    f"{exc.__class__.__name__}: {str(exc)[:240]}",
                    flush=True,
                )
                # We already possess the valid route, so unlike the previous guard
                # there is no reason to calculate it a second time.
                result = logistics_guard._mark_degraded(
                    result,
                    data,
                    v3,
                    category,
                    exc,
                )

        result = _rebalance_stage_count(result, state.intent)
        if (result.get("planner") or {}).get("stage_rebalanced"):
            state.phases.append("stages:rebalanced")
        state.phases.append("finalize")
        return _mark_pipeline(result, state)

    v3._build = build


__all__ = [
    "PIPELINE_VERSION",
    "PlanningState",
    "install_planning_pipeline",
    "_build_backbone",
    "_preload_canonical_stays",
    "_rebalance_stage_count",
    "_relation_candidate_loop_allowed",
]
