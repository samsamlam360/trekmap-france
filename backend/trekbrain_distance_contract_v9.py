"""Honest, route-preserving disclosure when a planned hiking day exceeds the goal.

Do not make an already calculated pedestrian route shorter on paper, rewrite
daily distances, relax the routing budget, or fabricate shelters / water.
This is a safety and UX contract, NOT a planner or quality-score override.
"""
from __future__ import annotations

import math
from typing import Any
from .trekbrain_distance_tolerance_v9 import intent_daily_bounds

# A hike longer by only a few hundred metres is routine GPS uncertainty;
# deviations above both +18% and +2 km are worth surfacing prominently.
EXCESS_RELATIVE_THRESHOLD = 0.18
EXCESS_ABSOLUTE_KM = 2.0
MAX_DAY_SLACK_KM = 0.15


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def annotate_daily_distance(result: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    """Annotate an existing hike with honest requested-vs-real daily distances.

    Only adds optional warnings and planner metadata. Never changes routes,
    stages' measured km, logistics, night allocations or returned status.
    Idempotent under wrappers or request reprocessing.
    """
    if not isinstance(result, dict):
        return result
    target = _number((intent or {}).get("daily_target"))
    daily_max = _number((intent or {}).get("daily_max"))
    stages = result.get("stages")
    if target is None or not isinstance(stages, list) or not stages:
        return result
    requested_days = (intent or {}).get("days")
    try:
        requested_days = int(requested_days)
    except (TypeError, ValueError):
        requested_days = len(stages)
    if requested_days != len(stages):
        # Number of daily segments unresolved: a separate planning issue.
        return result
    values = [_number(stage.get("distance_km")) if isinstance(stage, dict) else None for stage in stages]
    if any(x is None for x in values):
        return result

    actual = [float(x) for x in values]
    declared_min, declared_max = intent_daily_bounds(intent)
    explicit_bounds = declared_min is not None or declared_max is not None
    maximum = declared_max if declared_max is not None else daily_max
    worst = max(actual)
    avg = sum(actual) / len(actual)
    excess_days = []
    short_days = []
    for i, km in enumerate(actual):
        proportion_excess = km / target - 1.0
        exceeds_goal = proportion_excess > EXCESS_RELATIVE_THRESHOLD and km - target >= EXCESS_ABSOLUTE_KM
        slack = 0.0 if declared_max is not None else MAX_DAY_SLACK_KM
        exceeds_bound = (maximum is not None and km > maximum + slack + 1e-6
                         and (declared_max is not None or not explicit_bounds))
        if exceeds_goal or exceeds_bound:
            excess_days.append({
                "day": i + 1,
                "distance_km": round(km, 1),
                "extra_pct": round(max(0.0, proportion_excess) * 100),
                "exceeds_limit": bool(exceeds_bound),
            })
        if declared_min is not None and km < declared_min - 1e-6:
            short_days.append({
                "day": i + 1, "distance_km": round(km, 1),
                "minimum_km": declared_min, "below_minimum": True,
            })

    planner = result.setdefault("planner", {})
    if isinstance(planner, dict):
        search = planner.get("distance_search") or {}
        suggestions = []
        if excess_days:
            # This is a concrete *new planning request*, not a promise that
            # dividing the total creates usable overnight stops or safe stages.
            # Every proposed edit must rerun stage and logistics validation.
            suggested_days = max(len(stages) + 1, math.ceil(sum(actual) / target))
            suggestions.append({
                "type": "edit_request",
                "action": "increase_duration",
                "changes": {"days": suggested_days},
                "average_km_if_rebalanced": round(sum(actual) / suggested_days, 1),
                "preserves_existing_route": True,
                "requires_replan_and_validation": True,
                "label": f"Recalculer en {suggested_days} jours pour viser {sum(actual) / suggested_days:.1f} km/jour en moyenne.",
            })
            if not explicit_bounds:
                suggestions.append({
                    "type": "edit_request",
                    "action": "adjust_daily_distance",
                    "changes": {"daily_km": round(avg, 1)},
                    "longest_day_km": round(worst, 1),
                    "requires_replan_and_validation": True,
                    "label": f"Recalculer avec un objectif de {avg:.1f} km/jour ; le trajet actuel atteint {worst:.1f} km sur sa journée la plus longue.",
                })
        if short_days:
            shorter_duration = max(1, min(len(stages) - 1, math.floor(sum(actual) / declared_min)))
            suggestions.append({
                "type": "edit_request", "action": "decrease_duration",
                "changes": {"days": shorter_duration},
                "average_km_if_rebalanced": round(sum(actual) / shorter_duration, 1),
                "preserves_existing_route": True, "requires_replan_and_validation": True,
                "label": f"Demander un autre tracé ou recalculer en {shorter_duration} jours, puis vérifier le minimum de {declared_min:.1f} km sur chaque étape.",
            })
        planner["distance_contract"] = {
            "daily_target_km": round(target, 1),
            "daily_max_km": round(maximum, 1) if maximum is not None else None,
            "daily_min_km": round(declared_min, 1) if declared_min is not None else None,
            "explicit_daily_min_km": declared_min,
            "explicit_daily_max_km": declared_max,
            "actual_average_km": round(avg, 1),
            "longest_day_km": round(worst, 1),
            "days_exceeding": excess_days,
            "days_below_minimum": short_days,
            "target_exceeded": bool(excess_days),
            "status": "limit_exceeded" if short_days or any(row["exceeds_limit"] for row in excess_days) else "target_exceeded" if excess_days else "within_target",
            "distance_tolerance": "explicit" if explicit_bounds else "approximate",
            "explicit_bounds": explicit_bounds,
            "bounds_satisfied": not short_days and not any(row["exceeds_limit"] for row in excess_days),
            "adjustment_required": bool(excess_days or short_days),
            "suggestions": suggestions,
            "alternative_search": dict(search) if isinstance(search, dict) else {},
            "route_unchanged": True,
        }
    if not excess_days and not short_days:
        return result

    rendered = ", ".join(
        f"J{row['day']} : {row['distance_km']:.1f} km"
        for row in excess_days
    )
    notice = (
        f"Distance demandée dépassée : {rendered} pour un objectif de "
        f"{target:.1f} km/jour. Vérifie ta capacité et adapte la durée ou "
        "la distance avant de partir."
    ) if excess_days else (
        "Minimum demandé non respecté : "
        + ", ".join(f"J{row['day']} : {row['distance_km']:.1f} km" for row in short_days)
        + f" pour un minimum de {declared_min:.1f} km/jour."
    )
    if excess_days and short_days:
        notice += f" Certaines étapes sont aussi en dessous du minimum de {declared_min:.1f} km/jour."
    if isinstance(planner, dict):
        suggestions = planner["distance_contract"]["suggestions"]
        if suggestions:
            notice += " " + suggestions[0]["label"] + " Les étapes et les nuitées doivent être validées à nouveau."

    # A warning must remain visible on the stage card even if the user does
    # not expand technical analysis. Existing warnings are kept intact.
    for row in excess_days:
        stage = stages[row["day"] - 1]
        stage_notice = (
            f"⚠️ Distance au-dessus de l'objectif : {row['distance_km']:.1f} km "
            f"au lieu d'environ {target:.1f} km"
            + (f" (+{row['extra_pct']} %)." if row["extra_pct"] > 0 else ".")
        )
        current = str(stage.get("safety_notes") or "").strip()
        if stage_notice not in current:
            stage["safety_notes"] = (current + " " + stage_notice).strip()
    for row in short_days:
        stage = stages[row["day"] - 1]
        stage_notice = f"⚠️ Distance en dessous du minimum demandé : {row['distance_km']:.1f} km pour un minimum de {declared_min:.1f} km."
        current = str(stage.get("safety_notes") or "").strip()
        if stage_notice not in current:
            stage["safety_notes"] = (current + " " + stage_notice).strip()

    # The v8/v9 heuristic already penalises the measured stage distances.
    # Adding this presentation-only warning to confidence.limitations would
    # impose another -2 points per limitation and create an artificial quality
    # regression (Huelgoat 59.0 -> 57.1) without any route change.
    # Stage notes + advisor_notes + structured distance_contract carry the
    # warning to the user without modifying the underlying quality score.
    notes = result.get("advisor_notes")
    if isinstance(notes, list) and notice not in notes:
        notes.append(notice)
    return result


__all__ = ["annotate_daily_distance"]
