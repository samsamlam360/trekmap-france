"""Resilience layer for TrekBrain v9 campsite loops and long ORS round-trips.

Two production failures are handled here without weakening route validation:
- ORS Matrix may return HTTP 500 even while Directions still works. In that
  case we rank a few campsite cycles geometrically, then validate every chosen
  cycle with the normal ORS Directions API before exposing it.
- ORS round-trip requests are intentionally kept below ~100 km. For a longer
  multi-day fallback, build two or three validated loop lobes and concatenate
  them at the common start instead of failing immediately.

Straight-line distances are only a ranking/lower-bound heuristic. They are never
presented as hiking distance and never make a route safe by themselves.
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException

_INSTALLED = False


def _air_km(roundtrip, a: dict[str, Any], b: dict[str, Any]) -> float:
    return float(roundtrip._haversine(
        [float(a["lat"]), float(a["lon"])],
        [float(b["lat"]), float(b["lon"])],
    ))


def _geometry_solutions(campsite_loop, roundtrip, start, stays, days: int, target: float, low: float, high: float, width: int = 80):
    """Rank campsite cycles cheaply when Matrix is unavailable.

    Air distance is used only to discard combinations that are *certainly* too
    long and to prioritize likely candidates. The final candidate must still be
    routed by ORS Directions and pass the real per-stage distance gate.
    """
    nights = max(0, int(days) - 1)
    if nights <= 0 or len(stays) < nights:
        return []

    pool = list(stays[:16])
    hard_max = float(high) + 0.35
    beam = [(0.0, [], [], start)]  # score, selected, heuristic legs, last point

    for night in range(nights):
        expanded = []
        for score, selected, legs, last in beam:
            used = {str(x.get("source_url") or x.get("name") or id(x)) for x in selected}
            for stay in pool:
                key = str(stay.get("source_url") or stay.get("name") or id(stay))
                if key in used:
                    continue
                air = _air_km(roundtrip, last, stay)
                # Walking distance cannot be shorter than straight-line distance.
                if air <= 0.15 or air > hard_max:
                    continue
                remaining_days = days - (night + 1)
                back_air = _air_km(roundtrip, stay, start)
                if back_air > remaining_days * hard_max + 0.5:
                    continue
                estimated = air * 1.18
                short = max(0.0, float(low) - estimated)
                radial = float(stay.get("_radial_km") or _air_km(roundtrip, start, stay))
                expanded.append((
                    score + abs(estimated - target) * 1.25 + short * 0.45 + abs(radial - target * 0.75) * 0.08,
                    selected + [stay],
                    legs + [estimated],
                    stay,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda row: row[0])
        beam = expanded[:width]

    finals = []
    total_target = float(target) * int(days)
    for score, selected, legs, last in beam:
        back_air = _air_km(roundtrip, last, start)
        if back_air <= 0.15 or back_air > hard_max:
            continue
        final_estimated = back_air * 1.18
        all_legs = legs + [final_estimated]
        shape = float(campsite_loop._shape_ratio(start, selected))
        if days >= 3 and shape < 0.0007:
            continue
        total = sum(all_legs)
        spread = max(all_legs) - min(all_legs)
        score += (
            abs(final_estimated - target) * 1.25
            + abs(total - total_target) * 0.22
            + spread * 0.12
            - min(shape * 120.0, 3.0)
        )
        finals.append((score, selected, all_legs, shape))
    finals.sort(key=lambda row: row[0])
    return finals[:8]


def _recover_without_matrix(data, legacy_main, v3, roundtrip, ors, campsite_loop, matrix_warning: str):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        raise HTTPException(status_code=422, detail="Le secours sans matrice ne s'applique qu'aux boucles.")

    category = "camping" if intent.get("accommodation") == "camping" else "refuge" if intent.get("accommodation") == "refuge" else None
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    if not category or days <= 1:
        raise HTTPException(status_code=422, detail="Aucune nuitée structurée à récupérer.")

    location = v3._location(data)
    start = campsite_loop._start_for(v3, location)
    target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    low = float(intent.get("daily_min") or target * 0.75)
    high = float(intent.get("daily_max") or target * 1.25)

    stays = list(campsite_loop._diverse_stays(v3, roundtrip, start, category, days, target))[:16]
    if len(stays) < days - 1:
        raise HTTPException(
            status_code=422,
            detail=f"Le service Matrix est indisponible et seulement {len(stays)} nuitée(s) ont été trouvées pour {days - 1} nuit(s).",
        )

    solutions = _geometry_solutions(campsite_loop, roundtrip, start, stays, days, target, low, high)
    if not solutions:
        raise HTTPException(
            status_code=422,
            detail="ORS Matrix est indisponible et aucun ordre de campings plausible n'a pu être présélectionné sans dépasser la distance maximale.",
        )

    errors = []
    for _score, selected, _estimated_legs, _shape in solutions[:3]:
        route_points = [start] + selected + [start]
        routed = ors.get_route(
            [[float(p["lat"]), float(p["lon"])] for p in route_points],
            legacy_main.distance_gps,
        )
        if routed.get("fallback") is not False:
            errors.append(str(routed.get("warning") or "Directions indisponible"))
            continue

        final_coords = routed.get("coords") or []
        boundaries = [start] + selected + [start]
        stage_distances = v3._stage_distances(
            final_coords, boundaries, legacy_main, float(routed.get("distance") or 0)
        )
        if len(stage_distances) != days:
            continue
        if any(float(d) > high + 0.35 for d in stage_distances):
            errors.append(f"étape finale {max(stage_distances):.1f} km > {high:.1f} km")
            continue

        routed["routing_mode"] = "ors-camping-directions-loop"
        result = campsite_loop._render_result(
            data, legacy_main, v3, ors, intent, location,
            start, routed, selected, stage_distances,
        )
        result["planner_fallback"] = "ors-camping-directions-loop"
        result["route_preview"]["routing_mode"] = "ors-camping-directions-loop"
        notes = result.setdefault("advisor_notes", [])
        notes.insert(0, "ORS Matrix était indisponible ; les campings ont été présélectionnés localement puis chaque distance finale a été validée par ORS Directions.")
        if matrix_warning:
            result.setdefault("confidence", {}).setdefault("limitations", []).append(matrix_warning[:180])
        return result

    detail = " ; ".join(errors[:2])
    raise HTTPException(
        status_code=503,
        detail=(
            "ORS Matrix est indisponible et les quelques boucles de campings testées n'ont pas pu être validées par ORS Directions."
            + (f" Détails : {detail}." if detail else "")
        ),
    )


def _multi_lobe_roundtrip(roundtrip, start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    """Build >100 km fallback as several validated ORS round-trip lobes."""
    target_km = float(target_km)
    pieces = max(2, int(math.ceil(target_km / 90.0)))
    if pieces > 3:
        raise HTTPException(
            status_code=422,
            detail="Le secours automatique peut construire jusqu'à environ 270 km. Pour un trek plus long, indique une zone ou des étapes intermédiaires.",
        )
    piece_target = target_km / pieces
    merged = []
    total = 0.0
    warnings = []
    seeds = (3, 11, 29, 47, 61, 73)

    for index in range(pieces):
        route = None
        warning = None
        # One normal attempt plus one alternate seed only if necessary.
        for seed in (seeds[index * 2], seeds[index * 2 + 1]):
            route, warning = roundtrip._roundtrip_request(start, piece_target, seed)
            if route is not None:
                break
            if warning:
                warnings.append(warning)
        if route is None:
            detail = warning or (warnings[-1] if warnings else "OpenRouteService n'a pas généré la sous-boucle.")
            raise HTTPException(status_code=503, detail=detail)

        coords = list(route.get("coords") or [])
        if len(coords) < 2:
            raise HTTPException(status_code=503, detail="Une sous-boucle ORS n'a pas fourni de géométrie exploitable.")
        if merged and coords and merged[-1] == coords[0]:
            coords = coords[1:]
        merged.extend(coords)
        total += float(route.get("distance") or 0)

    if len(merged) < 2:
        raise HTTPException(status_code=503, detail="Le secours multi-boucles n'a produit aucune géométrie exploitable.")
    return {
        "coords": merged,
        "distance": round(total, 2),
        "fallback": False,
        "routing_mode": "ors-round-trip-multilobe",
        "profile": getattr(roundtrip.ors, "ORS_PROFILE", "foot-hiking"),
        "round_trip_lobes": pieces,
        "requested_distance_km": round(target_km, 1),
    }


def install_matrix_resilience(campsite_loop, roundtrip) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_recover = campsite_loop._recover
    original_best_roundtrip = roundtrip._best_roundtrip

    def recover(data, legacy_main, v3, roundtrip_module, ors):
        try:
            return original_recover(data, legacy_main, v3, roundtrip_module, ors)
        except HTTPException as exc:
            detail = str(exc.detail or "")
            folded = detail.casefold()
            matrix_failure = (
                exc.status_code >= 500
                and ("matrix" in folded or "matrice" in folded)
            ) or "matrix http 5" in folded
            if not matrix_failure:
                raise
            return _recover_without_matrix(
                data, legacy_main, v3, roundtrip_module, ors, campsite_loop, detail
            )

    def best_roundtrip(start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
        if float(target_km) <= 99.0:
            return original_best_roundtrip(start, target_km, daily_min, daily_max, days, v3)
        return _multi_lobe_roundtrip(
            roundtrip, start, target_km, daily_min, daily_max, days, v3
        )

    campsite_loop._recover = recover
    roundtrip._best_roundtrip = best_roundtrip


__all__ = [
    "install_matrix_resilience",
    "_geometry_solutions",
    "_recover_without_matrix",
    "_multi_lobe_roundtrip",
]
