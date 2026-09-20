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
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _cumulative(coords):
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + _haversine(a, b))
    return out


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
        anchors.append({
            "name": f"Repère jour {day}",
            "lat": float(coords[best][0]),
            "lon": float(coords[best][1]),
            "category": "route_anchor",
        })
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


def _nearest_unique_stays(v3, anchors, category: str, max_km: float = 2.6):
    chosen = []
    used = set()
    for anchor in anchors:
        try:
            rows = list(v3._nearby(anchor["lat"], anchor["lon"], max_km, [category]))
        except Exception:
            rows = []
        rows = [x for x in rows if x.get("category") == category]
        rows.sort(key=lambda x: v3._dist(anchor, x))
        stay = next((x for x in rows if (x.get("source_url") or x.get("name")) not in used), None)
        if not stay:
            return []
        used.add(stay.get("source_url") or stay.get("name"))
        chosen.append(stay)
    return chosen


def _build_roundtrip(data, legacy_main, v3):
    intent = v3._parse_intent(data)
    if v3._fold(intent.get("route_type") or "") != "boucle":
        raise HTTPException(status_code=422, detail="Le mode de secours round-trip ne s'applique qu'aux boucles.")
    if intent.get("via_query") or intent.get("end_query"):
        raise HTTPException(status_code=422, detail="La boucle de secours ne peut pas ignorer un passage ou une arrivée imposés.")

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

    days = max(1, int(intent.get("days") or data.days))
    target_km = float(intent.get("total_target") or float(intent.get("daily_target") or data.daily_km) * days)
    route = _best_roundtrip(
        start,
        target_km,
        float(intent.get("daily_min") or data.daily_km * 0.75),
        float(intent.get("daily_max") or data.daily_km * 1.25),
        days,
        v3,
    )
    coords = route.get("coords") or []
    anchors = _equal_anchors(coords, days)
    if len(anchors) != max(0, days - 1):
        raise HTTPException(status_code=422, detail="La boucle ORS n'a pas pu être découpée correctement en journées.")

    category = "camping" if intent.get("accommodation") == "camping" else "refuge" if intent.get("accommodation") == "refuge" else None
    stays = _nearest_unique_stays(v3, anchors, category) if category else []

    if category and days > 1:
        if len(stays) != days - 1:
            label = "campings" if category == "camping" else "hébergements"
            raise HTTPException(
                status_code=422,
                detail=f"La boucle pédestre existe, mais je n'ai pas trouvé assez de {label} à moins d'environ 2,6 km des fins d'étape.",
            )
        route_points = [start]
        for anchor, stay in zip(anchors, stays):
            route_points.extend([anchor, stay, anchor])
        route_points.append(start)
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

    daily_max = float(intent.get("daily_max") or 40)
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
        "advisor_notes": [
            "Planificateur avancé indisponible pour cette demande : boucle de secours calculée directement par ORS sur le réseau pédestre.",
            "Les distances sont réelles côté routage ; les services et conditions terrain restent à vérifier avant le départ.",
        ],
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


__all__ = ["install_roundtrip_fallback", "_build_roundtrip", "_equal_anchors", "_best_roundtrip"]
