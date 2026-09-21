"""ORS-native round-trip fallback for TrekBrain v9.

The normal planner remains the preferred path because it can optimise campsites,
GR corridors and POIs. This layer exists for the simpler promise that must still
work when ORS itself is healthy: create a real pedestrian loop around a known
place. It never accepts straight-line geometry.
"""
from __future__ import annotations

import math

import requests
from fastapi import HTTPException

from . import ors

_INSTALLED = False


def _haversine(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(dlat + lat1) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _cumulative(coords):
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + _haversine(a, b))
    return out


def _route_index_for_progress(cum, progress_km: float) -> int:
    if len(cum) <= 2:
        return 0
    return min(range(1, len(cum) - 1), key=lambda i: abs(float(cum[i]) - float(progress_km)))


def _route_anchor(coords, cum, index: int, name: str = "Repère de boucle") -> dict:
    index = max(0, min(int(index), len(coords) - 1))
    return {
        "name": name,
        "lat": float(coords[index][0]),
        "lon": float(coords[index][1]),
        "category": "route_anchor",
        "route_progress_km": round(float(cum[index]), 3) if cum else 0.0,
    }


def _equal_anchors(coords, days):
    if days <= 1 or len(coords) < 3:
        return []
    cum = _cumulative(coords)
    total = cum[-1]
    if total <= 0:
        return []
    anchors = []
    floor = 1
    for day in range(1, days):
        target = total * day / days
        choices = range(floor, len(cum) - 1)
        if not list(choices):
            return []
        best = min(range(floor, len(cum) - 1), key=lambda i: abs(cum[i] - target))
        anchors.append(_route_anchor(coords, cum, best, f"Repère jour {day}"))
        floor = min(best + 1, len(cum) - 2)
    return anchors


def _roundtrip_request(start, target_km: float, seed: int):
    if not ors.ORS_API_KEY:
        return None, "OpenRouteService non configuré : ORS_API_KEY est absente du serveur Render."
    payload = {
        "coordinates": [[float(start["lon"]), float(start["lat"])]],
        "instructions": False,
        "options": {
            "round_trip": {
                "length": int(round(target_km * 1000)),
                "points": 6,
                "seed": int(seed),
            }
        },
    }
    try:
        response = requests.post(
            ors.ORS_URL,
            json=payload,
            headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
            timeout=14,
        )
    except requests.Timeout:
        return None, "OpenRouteService round-trip : délai d'attente dépassé."
    except requests.RequestException as exc:
        return None, f"OpenRouteService round-trip inaccessible ({exc.__class__.__name__})."

    result, warning, _status = ors._parse_response(
        response,
        [[float(start["lat"]), float(start["lon"])]],
        lambda _coords: 0.0,
    )
    if result is None:
        return None, warning or "OpenRouteService n'a pas généré de boucle."
    result["routing_mode"] = "ors-round-trip"
    result["round_trip_seed"] = int(seed)
    return result, None


def _best_roundtrip(start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    if target_km > 99.0:
        raise HTTPException(
            status_code=422,
            detail="Le mode boucle automatique de secours est limité à environ 100 km au total.",
        )
    rows = []
    warnings = []
    for seed in (3, 11, 29):
        route, warning = _roundtrip_request(start, target_km, seed)
        if route is None:
            if warning:
                warnings.append(warning)
            continue
        distance = float(route.get("distance") or 0)
        per_day = distance / max(days, 1)
        retrace = float(v3._route_retrace_ratio(route.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
        range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
        rows.append((abs(distance - target_km) + range_penalty + retrace * 80, route))
    if not rows:
        detail = warnings[0] if warnings else "OpenRouteService n'a produit aucune boucle pédestre."
        raise HTTPException(status_code=503, detail=detail)
    rows.sort(key=lambda row: row[0])
    return rows[0][1]


def _stay_key(stay: dict) -> str:
    source = str(stay.get("source_url") or "").strip()
    if source:
        return source
    name = str(stay.get("name") or "").strip().casefold()
    try:
        return f"{name}|{float(stay['lat']):.5f}|{float(stay['lon']):.5f}"
    except Exception:
        return name


def _project_stay_to_route(coords, cum, stay: dict):
    try:
        point = [float(stay["lat"]), float(stay["lon"])]
    except Exception:
        return None
    if not coords:
        return None
    index = min(range(len(coords)), key=lambda i: _haversine(coords[i], point))
    return index, float(cum[index]), float(_haversine(coords[index], point))


def _nearby_stays(v3, anchor: dict, category: str, radius_km: float):
    try:
        rows = list(v3._nearby(anchor["lat"], anchor["lon"], radius_km, [category]))
    except Exception:
        rows = []
    return [dict(x) for x in rows if x.get("category") == category]


def _nearest_unique_stays(v3, anchors, category: str, max_km: float = 2.6):
    """Legacy exact-anchor lookup kept for compatibility and regressions."""
    chosen = []
    used = set()
    for anchor in anchors:
        rows = _nearby_stays(v3, anchor, category, max_km)
        rows.sort(key=lambda x: v3._dist(anchor, x))
        stay = next((x for x in rows if _stay_key(x) not in used), None)
        if not stay:
            return []
        used.add(_stay_key(stay))
        chosen.append(stay)
    return chosen


def _adaptive_stay_options(
    v3,
    coords,
    cum,
    target_progress: float,
    category: str,
    search_radius_km: float,
    window_km: float,
):
    """Find real stays around a section of the loop, not one arbitrary endpoint.

    Searching only at the mathematically exact daily split caused valid campsites
    a few kilometres earlier/later to be ignored. We now scan three points across
    a progress window, then project every stay back onto the ORS loop corridor.
    """
    if len(coords) < 3 or not cum:
        return []
    total = float(cum[-1])
    probes = []
    for progress in (target_progress - window_km, target_progress, target_progress + window_km):
        progress = max(0.2, min(total - 0.2, progress))
        idx = _route_index_for_progress(cum, progress)
        if idx not in probes:
            probes.append(idx)

    by_key = {}
    corridor_margin = window_km + search_radius_km + 1.0
    for idx in probes:
        anchor = _route_anchor(coords, cum, idx, "Recherche nuitée")
        for stay in _nearby_stays(v3, anchor, category, search_radius_km):
            projected = _project_stay_to_route(coords, cum, stay)
            if not projected:
                continue
            route_index, progress, offroute = projected
            if offroute > search_radius_km + 0.35:
                continue
            if abs(progress - target_progress) > corridor_margin:
                continue
            enriched = dict(stay)
            enriched["_route_index"] = int(route_index)
            enriched["_route_progress_km"] = float(progress)
            enriched["_offroute_km"] = float(offroute)
            key = _stay_key(enriched)
            quality = abs(progress - target_progress) + offroute * 0.75
            previous = by_key.get(key)
            if previous is None or quality < previous[0]:
                by_key[key] = (quality, enriched)

    rows = [value[1] for value in by_key.values()]
    rows.sort(key=lambda x: (
        abs(float(x.get("_route_progress_km") or 0) - target_progress)
        + float(x.get("_offroute_km") or 0) * 0.75
    ))
    return rows[:12]


def _range_penalty(distance: float, target: float, low: float, high: float) -> float:
    penalty = abs(float(distance) - float(target))
    if distance < low:
        penalty += (low - distance) * 8.0
    if distance > high:
        penalty += (distance - high) * 12.0
    return penalty


def _balanced_corridor_stays(
    v3,
    coords,
    days: int,
    category: str,
    daily_target: float,
    daily_min: float,
    daily_max: float,
):
    """Choose ordered stays that balance all days of the loop.

    A stay may sit a few kilometres before/after the ideal split and a few
    kilometres off the main corridor. The final geometry is still re-routed by
    ORS, and the hard daily-distance gate remains in force afterwards.
    """
    if days <= 1:
        return [], {"search_radius_km": 0.0, "window_km": 0.0, "options": []}
    cum = _cumulative(coords)
    if not cum or cum[-1] <= 0:
        return [], {"search_radius_km": 0.0, "window_km": 0.0, "options": []}

    total = float(cum[-1])
    search_radius = min(4.5, max(3.6, float(daily_target) * 0.22))
    window = min(8.0, max(5.0, float(daily_target) * 0.40))
    option_sets = []
    for night in range(1, days):
        target = total * night / days
        options = _adaptive_stay_options(
            v3, coords, cum, target, category, search_radius, window
        )
        option_sets.append(options)
        if not options:
            return [], {
                "search_radius_km": search_radius,
                "window_km": window,
                "options": [len(x) for x in option_sets],
            }

    # score, chosen, used keys, previous corridor progress, previous detour
    beam = [(0.0, [], frozenset(), 0.0, 0.0)]
    min_progress_gap = max(1.0, float(daily_min) * 0.22)
    for night_index, options in enumerate(option_sets, start=1):
        expanded = []
        target_progress = total * night_index / days
        for score, chosen, used, previous_progress, previous_detour in beam:
            for stay in options:
                key = _stay_key(stay)
                if key in used:
                    continue
                progress = float(stay.get("_route_progress_km") or 0)
                detour = float(stay.get("_offroute_km") or 0)
                if progress <= previous_progress + min_progress_gap:
                    continue
                estimated_stage = (progress - previous_progress) + previous_detour + detour
                stage_score = _range_penalty(estimated_stage, daily_target, daily_min, daily_max)
                placement_score = abs(progress - target_progress) * 0.30 + detour * 0.55
                expanded.append((
                    score + stage_score + placement_score,
                    chosen + [stay],
                    used | {key},
                    progress,
                    detour,
                ))
        if not expanded:
            return [], {
                "search_radius_km": search_radius,
                "window_km": window,
                "options": [len(x) for x in option_sets],
            }
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:36]

    finalists = []
    for score, chosen, used, previous_progress, previous_detour in beam:
        final_stage = (total - previous_progress) + previous_detour
        score += _range_penalty(final_stage, daily_target, daily_min, daily_max)
        finalists.append((score, chosen))
    finalists.sort(key=lambda row: row[0])
    return finalists[0][1] if finalists else [], {
        "search_radius_km": search_radius,
        "window_km": window,
        "options": [len(x) for x in option_sets],
    }


def _route_points_with_stays(coords, start: dict, stays, days: int):
    """Preserve the original ORS loop while inserting out-and-back stay detours."""
    cum = _cumulative(coords)
    if len(coords) < 3 or not cum:
        return [start, start]

    stay_by_index = {}
    for stay in stays:
        idx = int(stay.get("_route_index") or 0)
        idx = max(1, min(idx, len(coords) - 2))
        stay_by_index.setdefault(idx, []).append(stay)

    # Keep enough shape points to prevent ORS from shortcutting across the loop.
    shape_sections = max(8, int(days) * 3)
    shape_indices = {
        _route_index_for_progress(cum, cum[-1] * part / shape_sections)
        for part in range(1, shape_sections)
    }
    ordered_indices = sorted(shape_indices | set(stay_by_index))

    points = [dict(start)]
    for idx in ordered_indices:
        anchor = _route_anchor(coords, cum, idx, "Repère de boucle")
        points.append(anchor)
        for stay in stay_by_index.get(idx, []):
            points.append(dict(stay))
            points.append(dict(anchor))
    points.append(dict(start))
    return points


def _constraint_near_start(v3, query: str, location: str, start: dict, max_km: float = 3.0) -> bool:
    """Return True when an allegedly forced point is just the loop's own centre.

    Natural-language reconciliation can legitimately produce variants such as
    "Mont st Michel" versus "Mont Saint-Michel". Such a redundant waypoint
    should never disable ORS round-trip recovery.
    """
    query = str(query or "").strip()
    if not query:
        return True
    rows = []
    for candidate in (f"{query}, {location}, France", f"{query}, France", query):
        try:
            rows = v3._geocode(candidate) or []
        except Exception:
            rows = []
        if rows:
            break
    if not rows:
        return False
    try:
        return float(v3._dist(start, rows[0])) <= max_km
    except Exception:
        try:
            return _haversine(
                [float(start["lat"]), float(start["lon"])],
                [float(rows[0]["lat"]), float(rows[0]["lon"])],
            ) <= max_km
        except Exception:
            return False


def _build_roundtrip(data, legacy_main, v3):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        raise HTTPException(status_code=422, detail="Le mode de secours round-trip ne s'applique qu'aux boucles.")

    location = v3._location(data)
    geo = v3._geocode(f"{location}, France") or v3._geocode(location)
    if not geo:
        raise HTTPException(status_code=422, detail=f"Impossible de localiser « {location} ».")
    center = geo[0]
    start = {
        "name": str(center.get("name") or center.get("short_name") or location or "Départ"),
        "lat": float(center["lat"]),
        "lon": float(center["lon"]),
        "category": "place",
    }

    # Only genuinely different mandatory places block a one-point ORS round trip.
    # A parser-generated "passer par Mont-Saint-Michel" while the loop already
    # starts around Mont-Saint-Michel is redundant and must not kill recovery.
    forced = []
    for key, label in (("via_query", "passage"), ("end_query", "arrivée")):
        query = str(intent.get(key) or "").strip()
        if query and not _constraint_near_start(v3, query, location, start):
            forced.append((label, query))
    if forced:
        rendered = ", ".join(f"{label} « {query} »" for label, query in forced)
        raise HTTPException(
            status_code=422,
            detail=f"La boucle de secours ne peut pas ignorer une contrainte réellement distincte : {rendered}.",
        )

    days = max(1, int(intent.get("days") or data.days))
    daily_target = float(intent.get("daily_target") or data.daily_km)
    daily_min = float(intent.get("daily_min") or data.daily_km * 0.75)
    daily_max = float(intent.get("daily_max") or data.daily_km * 1.25)
    target_km = float(intent.get("total_target") or daily_target * days)
    route = _best_roundtrip(start, target_km, daily_min, daily_max, days, v3)
    coords = route.get("coords") or []
    anchors = _equal_anchors(coords, days)
    if len(anchors) != max(0, days - 1):
        raise HTTPException(status_code=422, detail="La boucle ORS n'a pas pu être découpée correctement en journées.")

    category = "camping" if intent.get("accommodation") == "camping" else "refuge" if intent.get("accommodation") == "refuge" else None
    stays = []
    stay_search = {"search_radius_km": 0.0, "window_km": 0.0, "options": []}

    if category and days > 1:
        stays, stay_search = _balanced_corridor_stays(
            v3, coords, days, category, daily_target, daily_min, daily_max
        )
        if len(stays) != days - 1:
            label = "campings" if category == "camping" else "hébergements"
            radius = float(stay_search.get("search_radius_km") or 0)
            window = float(stay_search.get("window_km") or 0)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"La boucle pédestre existe, mais je n'ai pas trouvé une combinaison de {label} "
                    f"permettant d'équilibrer les étapes. J'ai cherché le long du corridor, jusqu'à environ "
                    f"{radius:.1f} km de celui-ci et ±{window:.1f} km autour de chaque fin d'étape idéale."
                ),
            )

        route_points = _route_points_with_stays(coords, start, stays, days)
        routed = ors.get_route([[p["lat"], p["lon"]] for p in route_points], legacy_main.distance_gps)
        if routed.get("fallback") is not False:
            raise HTTPException(status_code=503, detail=str(routed.get("warning") or "ORS n'a pas validé les détours vers les nuitées."))
        route = routed
        coords = route.get("coords") or []
        boundaries = [start] + stays + [start]
        accommodations = [dict(x) for x in stays]
    else:
        boundaries = [start] + anchors + [start]
        accommodations = []

    stage_distances = v3._stage_distances(coords, boundaries, legacy_main, float(route.get("distance") or 0))
    if len(stage_distances) != days:
        stage_distances = [float(route.get("distance") or 0) / days] * days

    if any(d > daily_max + 0.35 for d in stage_distances):
        raise HTTPException(
            status_code=422,
            detail=(
                "Une boucle pédestre a bien été calculée, mais au moins une journée reste trop longue "
                f"({max(stage_distances):.1f} km pour une limite de {daily_max:.1f} km)."
            ),
        )

    total_elevation = int(legacy_main.elevation_gain(coords) or 0)
    stages = []
    for i, distance in enumerate(stage_distances):
        overnight = "Fin du trek"
        if i < days - 1:
            if stays:
                overnight = str(stays[i].get("name") or "Camping")
            elif getattr(data, "require_accommodation", False):
                overnight = "Nuitée à confirmer près de l'étape"
            else:
                overnight = "Étape intermédiaire"
        stages.append({
            "day": i + 1,
            "name": f"Jour {i + 1}",
            "distance_km": round(float(distance), 1),
            "elevation_gain_m": round(total_elevation * float(distance) / max(float(route.get("distance") or 1), 1)),
            "overnight": overnight,
            "water_notes": "Disponibilité de l'eau à vérifier sur la carte et sur place." if getattr(data, "require_water", False) else "",
            "highlights": [],
        })

    end = dict(start)
    notes = [
        "Planificateur avancé indisponible pour cette demande : boucle de secours calculée directement par ORS sur le réseau pédestre.",
        "Les distances sont réelles côté routage ; les services et conditions terrain restent à vérifier avant le départ.",
    ]
    if stays:
        notes.append(
            "Les fins d'étape ont été adaptées aux campings réellement trouvés le long de la boucle, puis tous les détours ont été revalidés par ORS."
        )

    return {
        "name": f"Boucle randonnée autour de {location}",
        "region": location,
        "description": "Boucle générée directement sur le réseau pédestre OpenRouteService après échec du planificateur avancé.",
        "difficulty": intent.get("difficulty") or getattr(data, "difficulty", "medium"),
        "route_type": "Boucle",
        "duration_days": days,
        "distance_km": round(float(route.get("distance") or 0), 1),
        "elevation_gain_m": total_elevation,
        "start": start,
        "end": end,
        "stages": stages,
        "route_preview": {
            "coords": coords,
            "distance_km": round(float(route.get("distance") or 0), 2),
            "distance": round(float(route.get("distance") or 0), 2),
            "fallback": False,
            "routing_mode": route.get("routing_mode") or "ors-round-trip",
            "profile": route.get("profile") or ors.ORS_PROFILE,
        },
        "accommodations": accommodations,
        "water": [],
        "transport": {
            "outbound": f"Accès au départ à vérifier pour {location}." if getattr(data, "require_transit", False) else "",
            "return": f"Retour depuis le même secteur ({location}) à vérifier." if getattr(data, "require_transit", False) else "",
        },
        "points_of_interest": [],
        "advisor_notes": notes,
        "confidence": {
            "score": 78,
            "limitations": ["Boucle ORS de secours : moins optimisée pour les POI que le planificateur principal."],
        },
        "planner_fallback": "ors-round-trip",
    }


def install_roundtrip_fallback(v3) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_build = v3._build

    def build(data, legacy_main):
        try:
            return original_build(data, legacy_main)
        except HTTPException as original_error:
            try:
                return _build_roundtrip(data, legacy_main, v3)
            except HTTPException as fallback_error:
                if fallback_error.status_code >= 500:
                    raise fallback_error
                original_detail = str(getattr(original_error, "detail", original_error))
                fallback_detail = str(getattr(fallback_error, "detail", fallback_error))
                raise HTTPException(
                    status_code=getattr(original_error, "status_code", 422),
                    detail=f"{original_detail} Secours boucle ORS : {fallback_detail}",
                )

    v3._build = build


__all__ = [
    "install_roundtrip_fallback",
    "_build_roundtrip",
    "_equal_anchors",
    "_best_roundtrip",
    "_constraint_near_start",
    "_balanced_corridor_stays",
    "_route_points_with_stays",
]
