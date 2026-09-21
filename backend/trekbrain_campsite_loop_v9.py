"""Campsite-first recovery for TrekBrain v9.

When the first ORS loop is walkable but misses useful campsites, do not keep
asking the round-trip endpoint for cosmetic variants.  The public ORS service can
return HTTP 500 for some long round-trip seeds, and more retries only waste the
interactive budget.

Recovery now works the other way around:
1. fetch one broad pool of real campsites/refuges around the start;
2. ask ORS Matrix once for real walking distances between start + stays;
3. solve the whole multi-day loop on that matrix;
4. request one final detailed ORS route through the selected nights.

No straight-line distance is accepted as route feasibility.
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import HTTPException

_INSTALLED = False


def _start_for(v3, location: str) -> dict[str, Any]:
    geo = v3._geocode(f"{location}, France") or v3._geocode(location)
    if not geo:
        raise HTTPException(status_code=422, detail=f"Impossible de localiser « {location} ».")
    center = geo[0]
    return {
        "name": str(center.get("name") or center.get("short_name") or location or "Départ"),
        "lat": float(center["lat"]),
        "lon": float(center["lon"]),
        "category": "place",
    }


def _stay_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or f"{item.get('name')}:{item.get('lat')}:{item.get('lon')}")


def _bearing(center: dict[str, Any], point: dict[str, Any]) -> float:
    lat1 = math.radians(float(center["lat"]))
    lat2 = math.radians(float(point["lat"]))
    dlon = math.radians(float(point["lon"]) - float(center["lon"]))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.atan2(y, x) + 2 * math.pi) % (2 * math.pi)


def _diverse_stays(v3, roundtrip, start, category: str, days: int, daily_target: float):
    """One broad OSM lookup, then keep geographically diverse stays locally."""
    needed = max(1, days - 1)
    search_radius = min(30.0, max(18.0, daily_target * 1.55))
    rows = list(roundtrip._nearby_stays(v3, start, category, search_radius))

    deduped = []
    seen = set()
    for row in rows:
        key = _stay_key(row)
        if key in seen:
            continue
        seen.add(key)
        try:
            radial = float(v3._dist(start, row))
        except Exception:
            try:
                radial = float(roundtrip._haversine(
                    [float(start["lat"]), float(start["lon"])],
                    [float(row["lat"]), float(row["lon"])],
                ))
            except Exception:
                continue
        if radial < 0.8 or radial > search_radius + 0.3:
            continue
        enriched = dict(row)
        enriched["_radial_km"] = radial
        enriched["_bearing"] = _bearing(start, enriched)
        enriched["_start_lat"] = float(start["lat"])
        enriched["_start_lon"] = float(start["lon"])
        deduped.append(enriched)

    if len(deduped) <= 20:
        return deduped

    # Preserve angular spread.  Nearest-only sampling tends to put every camp on
    # the same road and recreates an out-and-back loop.
    sectors = [[] for _ in range(8)]
    for stay in deduped:
        sector = int(float(stay["_bearing"]) / (2 * math.pi) * len(sectors)) % len(sectors)
        sectors[sector].append(stay)
    for sector in sectors:
        sector.sort(key=lambda x: abs(float(x["_radial_km"]) - daily_target * 0.75))

    selected = []
    index = 0
    while len(selected) < 20 and any(index < len(s) for s in sectors):
        for sector in sectors:
            if index < len(sector) and len(selected) < 20:
                selected.append(sector[index])
        index += 1
    return selected


def _shape_ratio(start: dict[str, Any], selected: list[dict[str, Any]]) -> float:
    if len(selected) < 2:
        return 0.0
    lat0 = math.radians(float(start["lat"]))

    def xy(point):
        return (
            (float(point["lon"]) - float(start["lon"])) * 111.320 * math.cos(lat0),
            (float(point["lat"]) - float(start["lat"])) * 110.574,
        )

    pts = [xy(start)] + [xy(x) for x in selected] + [xy(start)]
    area2 = 0.0
    perimeter = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        area2 += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)
    return abs(area2) / 2.0 / max(perimeter * perimeter, 1e-6)


def _matrix_solutions(matrix, stays, start, days: int, target: float, low: float, high: float, width: int = 140):
    """Beam-search campsite cycles using only real ORS Matrix distances."""
    nights = days - 1
    if nights <= 0 or len(stays) < nights or not matrix:
        return []
    hard_max = high + 0.35
    total_target = target * days
    beam = [(0.0, [], [], 0)]  # score, matrix indexes, legs, last index

    for night in range(nights):
        expanded = []
        for score, chosen, legs, last in beam:
            used = set(chosen)
            for idx in range(1, len(stays) + 1):
                if idx in used:
                    continue
                try:
                    leg = matrix[last][idx]
                    back = matrix[idx][0]
                except (IndexError, TypeError):
                    continue
                if leg is None or back is None:
                    continue
                leg = float(leg)
                back = float(back)
                if leg <= 0.2 or leg > hard_max:
                    continue
                remaining_days = days - (night + 1)
                if back > remaining_days * hard_max + 0.5:
                    continue
                short = max(0.0, low - leg)
                future = abs(back - remaining_days * target)
                expanded.append((
                    score + abs(leg - target) * 1.55 + short * 1.2 + future * 0.10,
                    chosen + [idx], legs + [leg], idx,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda row: row[0])
        beam = expanded[:width]

    finals = []
    for score, chosen, legs, last in beam:
        final_leg = matrix[last][0]
        if final_leg is None:
            continue
        final_leg = float(final_leg)
        if final_leg <= 0.2 or final_leg > hard_max:
            continue
        selected = [stays[i - 1] for i in chosen]
        shape = _shape_ratio(start, selected)
        if days >= 3 and shape < 0.0012:
            continue
        all_legs = legs + [final_leg]
        total = sum(all_legs)
        spread = max(all_legs) - min(all_legs)
        final_score = (
            score + abs(final_leg - target) * 1.55
            + max(0.0, low - final_leg) * 1.2
            + abs(total - total_target) * 0.35
            + spread * 0.30
            - min(shape * 140.0, 4.5)
        )
        finals.append((final_score, selected, all_legs, shape))
    finals.sort(key=lambda row: row[0])
    return finals[:8]


def _render_result(data, legacy_main, v3, ors, intent, location, start, route, stays, stage_distances):
    coords = route.get("coords") or []
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    total_distance = float(route.get("distance") or 0)
    total_elevation = int(legacy_main.elevation_gain(coords) or 0)

    stages = []
    for i, distance in enumerate(stage_distances):
        overnight = "Fin du trek" if i == days - 1 else str(stays[i].get("name") or "Camping")
        stages.append({
            "day": i + 1,
            "name": f"Jour {i + 1}",
            "distance_km": round(float(distance), 1),
            "elevation_gain_m": round(total_elevation * float(distance) / max(total_distance, 1.0)),
            "overnight": overnight,
            "water_notes": "Disponibilité de l'eau à vérifier sur la carte et sur place." if getattr(data, "require_water", False) else "",
            "highlights": [],
        })

    return {
        "name": f"Boucle randonnée autour de {location}",
        "region": location,
        "description": "Boucle construite en choisissant d'abord des campings réellement reliés à pied, puis validée par OpenRouteService.",
        "difficulty": intent.get("difficulty") or getattr(data, "difficulty", "medium"),
        "route_type": "Boucle",
        "duration_days": days,
        "distance_km": round(total_distance, 1),
        "elevation_gain_m": total_elevation,
        "start": dict(start),
        "end": dict(start),
        "stages": stages,
        "route_preview": {
            "coords": coords,
            "distance_km": round(total_distance, 2),
            "distance": round(total_distance, 2),
            "fallback": False,
            "routing_mode": "ors-camping-matrix-loop",
            "profile": route.get("profile") or ors.ORS_PROFILE,
        },
        "accommodations": [dict(x) for x in stays],
        "water": [],
        "transport": {
            "outbound": f"Accès au départ à vérifier pour {location}." if getattr(data, "require_transit", False) else "",
            "return": f"Retour depuis le même secteur ({location}) à vérifier." if getattr(data, "require_transit", False) else "",
        },
        "points_of_interest": [],
        "advisor_notes": [
            "La première boucle pédestre passait mal par les campings disponibles.",
            "TrekBrain a donc choisi les nuitées d'abord avec une matrice de distances pédestres réelles, puis a construit la boucle à travers elles.",
            "Le tracé détaillé et toutes les distances finales ont ensuite été revalidés par OpenRouteService.",
        ],
        "confidence": {
            "score": 82,
            "limitations": ["Ouverture et disponibilité des campings à vérifier avant le départ."],
        },
        "planner_fallback": "ors-camping-matrix-loop",
    }


def _recover(data, legacy_main, v3, roundtrip, ors):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        raise HTTPException(status_code=422, detail="La récupération camping-first ne s'applique qu'aux boucles.")

    category = "camping" if intent.get("accommodation") == "camping" else "refuge" if intent.get("accommodation") == "refuge" else None
    days = max(1, int(intent.get("days") or getattr(data, "days", 1) or 1))
    if not category or days <= 1:
        raise HTTPException(status_code=422, detail="Aucune nuitée structurée à récupérer.")

    location = v3._location(data)
    start = _start_for(v3, location)
    daily_target = float(intent.get("daily_target") or getattr(data, "daily_km", 18) or 18)
    daily_min = float(intent.get("daily_min") or daily_target * 0.75)
    daily_max = float(intent.get("daily_max") or daily_target * 1.25)

    stays = _diverse_stays(v3, roundtrip, start, category, days, daily_target)
    if len(stays) < days - 1:
        label = "campings" if category == "camping" else "hébergements"
        raise HTTPException(
            status_code=422,
            detail=f"Je n'ai trouvé que {len(stays)} {label} exploitables autour du départ, il en faut au moins {days - 1}.",
        )

    coords = [[float(start["lat"]), float(start["lon"])]] + [
        [float(x["lat"]), float(x["lon"])] for x in stays[:20]
    ]
    stays = stays[:20]
    matrix_result = ors.get_distance_matrix(coords)
    matrix = matrix_result.get("distances") if isinstance(matrix_result, dict) else None
    if not matrix:
        raise HTTPException(
            status_code=503,
            detail=str((matrix_result or {}).get("warning") or "ORS Matrix n'a pas fourni de distances pédestres."),
        )

    solutions = _matrix_solutions(
        matrix, stays, start, days, daily_target, daily_min, daily_max
    )
    if not solutions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"J'ai trouvé {len(stays)} nuitées possibles, mais aucune combinaison reliée à pied "
                f"ne donne {days} journées comprises dans environ {daily_min:.0f}–{daily_max:.0f} km."
            ),
        )

    errors = []
    for _score, selected, matrix_legs, _shape in solutions[:3]:
        route_points = [start] + selected + [start]
        routed = ors.get_route(
            [[float(p["lat"]), float(p["lon"])] for p in route_points],
            legacy_main.distance_gps,
        )
        if routed.get("fallback") is not False:
            errors.append(str(routed.get("warning") or "tracé final non routable"))
            continue

        final_coords = routed.get("coords") or []
        boundaries = [start] + selected + [start]
        stage_distances = v3._stage_distances(
            final_coords, boundaries, legacy_main, float(routed.get("distance") or 0)
        )
        if len(stage_distances) != days:
            stage_distances = [float(x) for x in matrix_legs]
        if len(stage_distances) != days:
            continue
        if any(float(d) > daily_max + 0.35 for d in stage_distances):
            errors.append(f"étape finale {max(stage_distances):.1f} km > {daily_max:.1f} km")
            continue

        routed["routing_mode"] = "ors-camping-matrix-loop"
        return _render_result(
            data, legacy_main, v3, ors, intent, location,
            start, routed, selected, stage_distances,
        )

    detail = " ; ".join(errors[:2])
    raise HTTPException(
        status_code=422,
        detail=(
            "La matrice a trouvé des combinaisons de nuitées plausibles, mais ORS n'a pas validé le tracé final."
            + (f" Détails : {detail}." if detail else "")
        ),
    )


def install_campsite_aware_roundtrip(v3, roundtrip, ors) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original = roundtrip._build_roundtrip

    def build_roundtrip(data, legacy_main, v3_module):
        try:
            return original(data, legacy_main, v3_module)
        except HTTPException as exc:
            detail = str(getattr(exc, "detail", exc)).casefold()
            campsite_failure = (
                "combinaison de campings" in detail
                or "combinaison de hébergements" in detail
                or "combinaison de hebergements" in detail
            )
            if not campsite_failure:
                raise
            try:
                return _recover(data, legacy_main, v3_module, roundtrip, ors)
            except HTTPException as recovery_error:
                original_detail = str(getattr(exc, "detail", exc))
                recovery_detail = str(getattr(recovery_error, "detail", recovery_error))
                raise HTTPException(
                    status_code=getattr(exc, "status_code", 422),
                    detail=f"{original_detail} Secours camping-first : {recovery_detail}",
                ) from recovery_error

    roundtrip._build_roundtrip = build_roundtrip


__all__ = [
    "install_campsite_aware_roundtrip", "_recover", "_diverse_stays",
    "_matrix_solutions", "_shape_ratio",
]
