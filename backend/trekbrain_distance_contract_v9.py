"""Honest, route-preserving disclosure when a planned hiking day exceeds the goal.

Do not make an already calculated pedestrian route shorter on paper, rewrite
daily distances, relax the routing budget, or fabricate shelters / water.
This is a safety and UX contract, NOT a planner or quality-score override.
"""
from __future__ import annotations

import math
from typing import Any

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
    worst = max(actual)
    avg = sum(actual) / len(actual)
    excess_days = []
    for i, km in enumerate(actual):
        proportion_excess = km / target - 1.0
        exceeds_goal = proportion_excess > EXCESS_RELATIVE_THRESHOLD and km - target >= EXCESS_ABSOLUTE_KM
        exceeds_bound = daily_max is not None and km > daily_max + MAX_DAY_SLACK_KM
        if exceeds_goal or exceeds_bound:
            excess_days.append({
                "day": i + 1,
                "distance_km": round(km, 1),
                "extra_pct": round(max(0.0, proportion_excess) * 100),
                "exceeds_limit": bool(exceeds_bound),
            })

    planner = result.setdefault("planner", {})
    if isinstance(planner, dict):
        planner["distance_contract"] = {
            "daily_target_km": round(target, 1),
            "daily_max_km": round(daily_max, 1) if daily_max is not None else None,
            "actual_average_km": round(avg, 1),
            "longest_day_km": round(worst, 1),
            "days_exceeding": excess_days,
            "target_exceeded": bool(excess_days),
            "route_unchanged": True,
        }
    if not excess_days:
        return result

    rendered = ", ".join(
        f"J{row['day']} : {row['distance_km']:.1f} km"
        for row in excess_days
    )
    notice = (
        f"Distance demandée dépassée : {rendered} pour un objectif de "
        f"{target:.1f} km/jour. Vérifie ta capacité et adapte la durée ou "
        "la distance avant de partir."
    )

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

    confidence = result.get("confidence")
    if isinstance(confidence, dict):
        limitations = confidence.setdefault("limitations", [])
        if isinstance(limitations, list) and notice not in limitations:
            limitations.append(notice)
    notes = result.get("advisor_notes")
    if isinstance(notes, list) and notice not in notes:
        notes.append(notice)
    return result


__all__ = ["annotate_daily_distance"]
