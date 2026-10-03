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


def _polyline_haversine(coords) -> float:
    return sum(_haversine(a, b) for a, b in zip(coords or [], (coords or [])[1:]))


def _merge_coords(prefix, connector):
    merged = [[float(p[0]), float(p[1])] for p in (prefix or []) if len(p) >= 2]
    for point in connector or []:
        row = [float(point[0]), float(point[1])]
        if not merged or row != merged[-1]:
            merged.append(row)
    return merged


def _destination(point, distance_km: float, bearing_deg: float):
    """Destination point on a spherical Earth, returned as [lat, lon]."""
    lat1 = math.radians(float(point[0]))
    lon1 = math.radians(float(point[1]))
    bearing = math.radians(float(bearing_deg))
    angular = float(distance_km) / 6371.0088
    sin_lat1, cos_lat1 = math.sin(lat1), math.cos(lat1)
    sin_ang, cos_ang = math.sin(angular), math.cos(angular)
    lat2 = math.asin(
        sin_lat1 * cos_ang + cos_lat1 * sin_ang * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * sin_ang * cos_lat1,
        cos_ang - sin_lat1 * math.sin(lat2),
    )
    lon2 = (lon2 + 3 * math.pi) % (2 * math.pi) - math.pi
    return [math.degrees(lat2), math.degrees(lon2)]


def _polygon_loop_candidates(start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    """Generate bounded waypoint loops and validate every metre through ORS.

    ORS round_trip can overshoot its requested length badly on constrained path
    networks. This fallback does not draw synthetic route geometry: it creates
    only three *targets* around the departure, then asks the normal pedestrian
    router to calculate the complete closed route through them.
    """
    start_coord = [float(start["lat"]), float(start["lon"])]
    feasible_low = max(3.0, float(daily_min) * max(days, 1))
    feasible_high = float(daily_max) * max(days, 1)
    # A 3-point fan has a straight geometric perimeter of roughly 3.8*r.
    # Dividing by ~5.5 leaves room for the normal network-vs-air inflation.
    radius = max(2.0, min(18.0, float(target_km) / 5.6))
    attempts = (
        (90.0, 1.00),   # east-facing fan, useful on many western coasts
        (180.0, 0.92),
        (0.0, 0.92),
        (270.0, 0.84),
    )
    variants = []
    for orientation, scale in attempts:
        r = radius * scale
        bearings = (orientation - 55.0, orientation, orientation + 55.0)
        targets = [_destination(start_coord, r, bearing) for bearing in bearings]
        routed = ors.get_route(
            [start_coord] + targets + [start_coord],
            _polyline_haversine,
        )
        if not isinstance(routed, dict) or routed.get("fallback") is not False:
            continue
        coords = routed.get("coords") or []
        if len(coords) < 4:
            continue
        try:
            distance = float(routed.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(distance) or distance <= 0:
            continue
        if _haversine(coords[-1], start_coord) > 0.15:
            continue
        retrace = float(v3._route_retrace_ratio(coords)) if hasattr(v3, "_route_retrace_ratio") else 0.0
        # Do not duplicate the central distance/retrace gates here. ORS may
        # produce a perfectly valid loop that looks mediocre to this local
        # heuristic but is still the closest feasible option. Keep every closed,
        # routed candidate and let _best_roundtrip apply the common scoring and
        # hard distance preference consistently.
        candidate = dict(routed)
        candidate.update({
            "distance": round(distance, 2),
            "fallback": False,
            "routing_mode": "ors-waypoint-loop",
            "profile": routed.get("profile") or ors.ORS_PROFILE,
            "provider": "OpenRouteService",
            "waypoint_loop": True,
            "waypoint_orientation_deg": round(orientation, 1),
            "waypoint_radius_km": round(r, 2),
            "requested_total_km": round(float(target_km), 2),
            "waypoint_retrace_ratio": round(retrace, 4),
        })
        variants.append(candidate)
        if feasible_low * 0.90 <= distance <= feasible_high + 0.35:
            # One genuinely feasible routed loop is enough to avoid wasting API
            # budget. Candidate ranking will still compare it with other rows.
            break
    return variants


def _matrix_subloop_candidates(route, start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    """Rank compact routed cycles through real points from an oversized ORS loop."""
    coords = [[float(p[0]), float(p[1])] for p in (route.get("coords") or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(coords) < 24:
        return []
    cum = _cumulative(coords)
    if not cum or cum[-1] <= 0:
        return []
    start_coord = [float(start["lat"]), float(start["lon"])]
    samples = []
    for fraction in [0.07 + 0.86 * i / 8 for i in range(9)]:
        idx = _route_index_for_progress(cum, cum[-1] * fraction)
        if 1 < idx < len(coords) - 2 and (not samples or idx != samples[-1][0]):
            samples.append((idx, float(cum[idx]) / float(cum[-1]), coords[idx]))
    if len(samples) < 5:
        return []
    points = [start_coord] + [x[2] for x in samples]
    result = ors.get_distance_matrix(points)
    matrix = result.get("distances") if isinstance(result, dict) else None
    if not isinstance(matrix, list) or len(matrix) != len(points):
        return []
    low = max(3.0, float(daily_min) * max(days, 1))
    high = float(daily_max) * max(days, 1)
    predicted = []
    lat0 = math.radians(start_coord[0])
    for i in range(len(samples) - 1):
        for j in range(i + 1, len(samples)):
            if samples[j][1] - samples[i][1] < 0.18:
                continue
            try:
                legs = (float(matrix[0][i+1]), float(matrix[i+1][j+1]), float(matrix[j+1][0]))
            except (IndexError, TypeError, ValueError):
                continue
            if not all(math.isfinite(x) and x > 0.05 for x in legs):
                continue
            a, b = samples[i][2], samples[j][2]
            ax=(a[1]-start_coord[1])*111.320*math.cos(lat0); ay=(a[0]-start_coord[0])*110.574
            bx=(b[1]-start_coord[1])*111.320*math.cos(lat0); by=(b[0]-start_coord[0])*110.574
            area2=abs(ax*by-bx*ay)
            perimeter=math.hypot(ax,ay)+math.hypot(bx-ax,by-ay)+math.hypot(bx,by)
            shape=area2/max(perimeter*perimeter,1e-6)
            if shape < 0.004:
                continue
            total=sum(legs)
            outside=max(0.0, low*0.90-total)*5 + max(0.0, total-high)*6
            predicted.append((abs(total-target_km)+outside-min(shape*40,2), i, j, total, shape))
    predicted.sort(key=lambda x:x[0])
    variants=[]
    for _, i, j, estimate, shape in predicted[:5]:
        routed=ors.get_route([start_coord, samples[i][2], samples[j][2], start_coord], _polyline_haversine)
        if not isinstance(routed,dict) or routed.get("fallback") is not False:
            continue
        rc=routed.get("coords") or []
        if len(rc)<4 or _haversine(rc[0],start_coord)>0.15 or _haversine(rc[-1],start_coord)>0.15:
            continue
        try: distance=float(routed.get("distance") or 0)
        except (TypeError,ValueError): continue
        retrace=float(v3._route_retrace_ratio(rc)) if hasattr(v3,"_route_retrace_ratio") else 0.0
        if not math.isfinite(distance) or distance<=0 or retrace>0.42:
            continue
        candidate=dict(routed)
        candidate.update({"distance":round(distance,2),"fallback":False,"routing_mode":"ors-matrix-subloop","matrix_subloop":True,"shortened_from_km":round(float(route.get("distance") or 0),2),"matrix_predicted_km":round(estimate,2),"matrix_shape_score":round(shape,4),"matrix_subloop_retrace":round(retrace,4)})
        variants.append(candidate)
        if low*0.90 <= distance <= high+0.35 or len(variants)>=2:
            break
    return variants


def _shortcut_oversized_loop(route, start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    """Shorten one oversized real loop with one ORS Matrix + one Directions call.

    Candidate endpoints are sampled directly on the already validated loop.
    ORS Matrix evaluates many possible network shortcuts in one request; only
    the best predicted pair is then rendered as detailed pedestrian geometry.
    This avoids the former burst of repeated Directions calls.
    """
    coords = [
        [float(p[0]), float(p[1])]
        for p in (route.get("coords") or [])
        if isinstance(p, (list, tuple)) and len(p) >= 2
    ]
    if len(coords) < 24:
        return []

    try:
        routed_total = float(route.get("distance") or 0)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(routed_total) or routed_total <= 0:
        return []

    feasible_low = max(3.0, float(daily_min) * max(days, 1))
    feasible_high = float(daily_max) * max(days, 1)
    if routed_total <= feasible_high + 0.35:
        return []

    cumulative = _cumulative(coords)
    geometric_total = float(cumulative[-1] or 0)
    if geometric_total <= 0:
        return []

    # Thirteen internal points fit comfortably inside ORS Matrix limits and give
    # dozens of possible arc replacements while keeping one network request.
    fractions = [0.07 + 0.86 * i / 12 for i in range(13)]
    sampled = []
    for fraction in fractions:
        idx = _route_index_for_progress(cumulative, geometric_total * fraction)
        if idx <= 1 or idx >= len(coords) - 2:
            continue
        if sampled and idx == sampled[-1][0]:
            continue
        sampled.append((idx, float(cumulative[idx]) / geometric_total, coords[idx]))
    if len(sampled) < 5:
        return []

    matrix_result = ors.get_distance_matrix([row[2] for row in sampled])
    matrix = matrix_result.get("distances") if isinstance(matrix_result, dict) else None
    if not isinstance(matrix, list) or len(matrix) != len(sampled):
        warning = str((matrix_result or {}).get("warning") or "")[:120] if isinstance(matrix_result, dict) else ""
        print(
            f"[TrekBrain v9][matrix-shortcut] matrix=unavailable "
            f"route_km={routed_total:.1f} target_km={float(target_km):.1f} "
            f"samples={len(sampled)} warning={warning!r}",
        flush=True,
        )
        return []

    predicted = []
    for i in range(len(sampled) - 1):
        a_idx, a_fraction, _a_coord = sampled[i]
        for j in range(i + 1, len(sampled)):
            b_idx, b_fraction, _b_coord = sampled[j]
            arc_fraction = b_fraction - a_fraction
            if arc_fraction < 0.18 or arc_fraction > 0.78:
                continue
            try:
                shortcut_km = matrix[i][j]
                shortcut_km = float(shortcut_km) if shortcut_km is not None else None
            except (IndexError, TypeError, ValueError):
                shortcut_km = None
            if shortcut_km is None or not math.isfinite(shortcut_km) or shortcut_km <= 0:
                continue

            removed_km = routed_total * arc_fraction
            # It must actually be a shortcut. A tiny saving is not worth
            # reshaping a route and tends to create noisy candidates.
            if shortcut_km >= removed_km - 0.8:
                continue
            retained_km = routed_total * (1.0 - arc_fraction)
            total = retained_km + shortcut_km
            distance_penalty = abs(total - float(target_km))
            if total < feasible_low * 0.88:
                distance_penalty += (feasible_low * 0.88 - total) * 4.0
            if total > feasible_high + 0.35:
                distance_penalty += (total - feasible_high) * 5.0
            # Prefer meaningful shortcuts without throwing away almost the whole
            # original loop.
            shape_penalty = max(0.0, arc_fraction - 0.66) * 12.0
            predicted.append((
                distance_penalty + shape_penalty,
                i, j, a_idx, b_idx, a_fraction, b_fraction,
                shortcut_km, total,
            ))

    if not predicted:
        print(
            f"[TrekBrain v9][matrix-shortcut] matrix=ok candidates=0 "
            f"route_km={routed_total:.1f} target_km={float(target_km):.1f} "
            f"samples={len(sampled)}",
        flush=True,
        )
        return []
    predicted.sort(key=lambda row: row[0])
    print(
        f"[TrekBrain v9][matrix-shortcut] matrix=ok candidates={len(predicted)} "
        f"route_km={routed_total:.1f} target_km={float(target_km):.1f} "
        f"best_predicted_km={float(predicted[0][8]):.1f}",
    flush=True,
    )

    start_coord = [float(start["lat"]), float(start["lon"])]
    variants = []
    # Usually the first pair is enough. A second render is allowed only if the
    # matrix estimate and detailed Directions geometry disagree materially.
    for row in predicted[:2]:
        _score, _i, _j, a_idx, b_idx, a_fraction, b_fraction, matrix_shortcut_km, _predicted_total = row
        connector = ors.get_route([coords[a_idx], coords[b_idx]], _polyline_haversine)
        if not isinstance(connector, dict) or connector.get("fallback") is not False:
            continue
        connector_coords = connector.get("coords") or []
        if len(connector_coords) < 2:
            continue
        try:
            connector_distance = float(connector.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(connector_distance) or connector_distance <= 0:
            continue

        retained_fraction = a_fraction + (1.0 - b_fraction)
        retained_distance = routed_total * retained_fraction
        total = retained_distance + connector_distance

        prefix = coords[: a_idx + 1]
        suffix = coords[b_idx:]
        merged = _merge_coords(prefix, connector_coords[1:])
        if suffix:
            merged = _merge_coords(
                merged,
                suffix[1:] if merged and suffix[0] == merged[-1] else suffix,
            )
        if len(merged) < 16:
            continue
        if _haversine(merged[0], start_coord) > 0.20 or _haversine(merged[-1], start_coord) > 0.20:
            continue

        retrace = float(v3._route_retrace_ratio(merged)) if hasattr(v3, "_route_retrace_ratio") else 0.0
        variants.append({
            "coords": merged,
            "distance": round(total, 2),
            "fallback": False,
            "routing_mode": "ors-matrix-arc-shortcut",
            "profile": connector.get("profile") or route.get("profile") or ors.ORS_PROFILE,
            "provider": "OpenRouteService",
            "shortened_from_km": round(routed_total, 2),
            "shortcut_arc_start": round(a_fraction, 3),
            "shortcut_arc_end": round(b_fraction, 3),
            "shortcut_matrix_km": round(matrix_shortcut_km, 2),
            "shortcut_connector_km": round(connector_distance, 2),
            "shortcut_retrace_ratio": round(retrace, 4),
            "matrix_shortcut": True,
        })
        if feasible_low * 0.90 <= total <= feasible_high + 0.35 and retrace <= 0.40:
            break
    if variants:
        best = min(variants, key=lambda row: abs(float(row.get("distance") or 0) - float(target_km)))
        print(
            f"[TrekBrain v9][matrix-shortcut] rendered={len(variants)} "
            f"best_actual_km={float(best.get('distance') or 0):.1f} "
            f"best_retrace={float(best.get('shortcut_retrace_ratio') or 0):.3f}",
        flush=True,
        )
    else:
        print(
            f"[TrekBrain v9][matrix-shortcut] rendered=0 "
            f"route_km={routed_total:.1f} target_km={float(target_km):.1f}",
        flush=True,
        )
    return variants


def _shorten_oversized_loop(route, start, target_km: float, daily_min: float, daily_max: float, days: int, v3):
    """Shorten a validated ORS loop without inventing straight-line geometry."""
    coords = [
        [float(p[0]), float(p[1])]
        for p in (route.get("coords") or [])
        if isinstance(p, (list, tuple)) and len(p) >= 2
    ]
    if len(coords) < 12:
        return []

    try:
        routed_total = float(route.get("distance") or 0)
    except (TypeError, ValueError):
        return []
    feasible_low = max(3.0, float(daily_min) * max(days, 1))
    feasible_high = float(daily_max) * max(days, 1)
    if routed_total <= feasible_high + 0.35:
        return []

    cumulative = _cumulative(coords)
    geometric_total = float(cumulative[-1] or 0)
    if geometric_total <= 0:
        return []

    ratio = max(0.20, min(0.90, float(target_km) / routed_total))
    fractions = []
    for factor in (0.78, 1.00, 1.20):
        value = max(0.18, min(0.88, ratio * factor))
        if all(abs(value - old) > 0.035 for old in fractions):
            fractions.append(value)

    start_coord = [float(start["lat"]), float(start["lon"])]
    variants = []
    for fraction in fractions:
        idx = _route_index_for_progress(cumulative, geometric_total * fraction)
        if idx <= 1 or idx >= len(coords) - 2:
            continue
        prefix = coords[: idx + 1]
        prefix_distance = routed_total * (float(cumulative[idx]) / geometric_total)
        connector = ors.get_route([coords[idx], start_coord], _polyline_haversine)
        if not isinstance(connector, dict) or connector.get("fallback") is not False:
            continue
        connector_coords = connector.get("coords") or []
        if len(connector_coords) < 2:
            continue
        try:
            connector_distance = float(connector.get("distance") or 0)
        except (TypeError, ValueError):
            continue
        total = prefix_distance + connector_distance
        if total < feasible_low * 0.90 or total > feasible_high + 0.35:
            continue

        merged = _merge_coords(prefix, connector_coords[1:])
        if len(merged) < 12 or _haversine(merged[-1], start_coord) > 0.12:
            continue
        retrace = float(v3._route_retrace_ratio(merged)) if hasattr(v3, "_route_retrace_ratio") else 0.0
        if retrace > 0.42:
            continue

        variants.append({
            "coords": merged,
            "distance": round(total, 2),
            "fallback": False,
            "routing_mode": "ors-round-trip-shortened",
            "profile": route.get("profile") or ors.ORS_PROFILE,
            "provider": "OpenRouteService",
            "shortened_from_km": round(routed_total, 2),
            "shortening_fraction": round(fraction, 3),
            "closing_route_km": round(connector_distance, 2),
        })
    return variants


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

    def add_candidate(requested_km: float, seed: int):
        route, warning = _roundtrip_request(start, requested_km, seed)
        if route is None:
            if warning:
                warnings.append(warning)
            return
        distance = float(route.get("distance") or 0)
        per_day = distance / max(days, 1)
        retrace = float(v3._route_retrace_ratio(route.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
        range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
        route["round_trip_requested_km"] = round(float(requested_km), 2)
        rows.append((abs(distance - target_km) + range_penalty + retrace * 80, route))

    for seed in (3, 11, 29):
        add_candidate(target_km, seed)

    # ORS round-trip length is a routing objective, not a guaranteed output.
    # Mountain networks can overshoot it strongly. If all first attempts sit
    # outside the feasible total range, calibrate one bounded second pass from
    # the observed provider ratio rather than rejecting an otherwise valid loop.
    if rows:
        feasible_low = max(3.0, float(daily_min) * max(days, 1))
        feasible_high = float(daily_max) * max(days, 1)
        best_observed = min(rows, key=lambda row: abs(float(row[1].get("distance") or 0) - target_km))[1]
        observed = float(best_observed.get("distance") or 0)
        # Calibration is useful when ORS undershoots. For oversized loops, the
        # round-trip endpoint has repeatedly shown that smaller requested lengths
        # can still return nearly the same large circuit. Go straight to the
        # matrix shortcut instead of spending two more round-trip requests.
        if observed > 0 and observed < feasible_low:
            correction = max(0.45, min(1.65, target_km / observed))
            calibrated = max(3.0, min(99.0, target_km * correction))
            if abs(calibrated - target_km) >= 2.0:
                add_candidate(calibrated, 7)

        # First try compact cycles through real points already proven routable
        # by the oversized ORS loop. This can shrink the circuit much more than
        # keeping most of the original arc.
        if all(float(row[1].get("distance") or 0) > feasible_high + 0.35 for row in rows):
            source = min(rows, key=lambda row: abs(float(row[1].get("distance") or 0) - target_km))[1]
            for variant in _matrix_subloop_candidates(
                source, start, target_km, daily_min, daily_max, days, v3
            ):
                distance = float(variant.get("distance") or 0)
                per_day = distance / max(days, 1)
                retrace = float(v3._route_retrace_ratio(variant.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
                range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
                rows.append((abs(distance - target_km) + range_penalty + retrace * 80, variant))

        feasible_now = [
            row for row in rows
            if feasible_low * 0.90 <= float(row[1].get("distance") or 0) <= feasible_high + 0.35
        ]

        # If no compact cycle fits, try replacing a large internal arc.
        if not feasible_now and all(float(row[1].get("distance") or 0) > feasible_high + 0.35 for row in rows):
            source = min(rows, key=lambda row: abs(float(row[1].get("distance") or 0) - target_km))[1]
            for variant in _shortcut_oversized_loop(
                source, start, target_km, daily_min, daily_max, days, v3
            ):
                distance = float(variant.get("distance") or 0)
                per_day = distance / max(days, 1)
                retrace = float(v3._route_retrace_ratio(variant.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
                range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
                rows.append((abs(distance - target_km) + range_penalty + retrace * 80, variant))

        # Keep the older cut-and-close recovery as a bounded fallback only when
        # Matrix could not produce a feasible circuit.
        feasible_now = [
            row for row in rows
            if feasible_low * 0.90 <= float(row[1].get("distance") or 0) <= feasible_high + 0.35
        ]
        if not feasible_now:
            source = min(
                rows,
                key=lambda row: abs(float(row[1].get("distance") or 0) - target_km),
            )[1]
            for variant in _shorten_oversized_loop(
                source, start, target_km, daily_min, daily_max, days, v3
            ):
                distance = float(variant.get("distance") or 0)
                per_day = distance / max(days, 1)
                retrace = float(v3._route_retrace_ratio(variant.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
                range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
                rows.append((
                    abs(distance - target_km) + range_penalty + retrace * 80,
                    variant,
                ))

        # If even on-network arc shortcuts miss the requested window, try the
        # explicit waypoint fan as the last bounded routing fallback.
        feasible_now = [
            row for row in rows
            if feasible_low * 0.90 <= float(row[1].get("distance") or 0) <= feasible_high + 0.35
        ]
        if not feasible_now:
            for variant in _polygon_loop_candidates(
                start, target_km, daily_min, daily_max, days, v3
            ):
                distance = float(variant.get("distance") or 0)
                per_day = distance / max(days, 1)
                retrace = float(v3._route_retrace_ratio(variant.get("coords") or [])) if hasattr(v3, "_route_retrace_ratio") else 0.0
                range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
                rows.append((
                    abs(distance - target_km) + range_penalty + retrace * 80,
                    variant,
                ))

    if not rows:
        detail = warnings[0] if warnings else "OpenRouteService n'a produit aucune boucle pédestre."
        raise HTTPException(status_code=503, detail=detail)

    # Distance constraints are a hard feasibility gate, not merely one term in
    # a soft score. A beautifully shaped 51 km loop must never beat a valid
    # 35 km loop when the user asked for about 32 km. Score candidates only
    # after preferring those that fit the requested multi-day distance window.
    feasible_low = max(3.0, float(daily_min) * max(days, 1))
    feasible_high = float(daily_max) * max(days, 1)
    feasible = [
        row for row in rows
        if feasible_low * 0.90 <= float(row[1].get("distance") or 0) <= feasible_high + 0.35
    ]
    pool = feasible or rows
    pool.sort(key=lambda row: row[0])
    selected = pool[0][1]
    selected["distance_window_preferred"] = bool(feasible)
    selected["candidate_pool_size"] = len(rows)
    selected["candidate_modes"] = sorted({
        str(row[1].get("routing_mode") or "unknown") for row in rows
    })
    return selected


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


def _roundtrip_stage_distances(coords, boundaries, stays, days: int, route_distance: float, legacy_main, v3):
    """Return reliable day distances for a closed fallback loop.

    For a plain round trip, intermediate boundaries come from _equal_anchors and
    already represent equal progress along the validated geometry. Re-locating
    those anchors by geographic proximity is unsafe on self-crossing loops: the
    same place can occur several times and the nearest-point lookup may select
    the wrong passage. In that case the mathematically correct split is simply
    the routed total divided by the requested number of days.

    When real overnight stays are inserted, their exact routed positions matter,
    so keep the full boundary-based stage measurement.
    """
    try:
        total = float(route_distance or 0)
    except (TypeError, ValueError):
        total = 0.0
    if not stays and days > 0 and math.isfinite(total) and total > 0:
        return [total / days] * days

    measured = v3._stage_distances(coords, boundaries, legacy_main, total)
    if len(measured) != days and total > 0:
        return [total / max(days, 1)] * max(days, 1)
    return measured


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

    stage_distances = _roundtrip_stage_distances(
        coords,
        boundaries,
        stays,
        days,
        float(route.get("distance") or 0),
        legacy_main,
        v3,
    )

    if any(d > daily_max + 0.35 for d in stage_distances):
        raise HTTPException(
            status_code=422,
            detail=(
                "Une boucle pédestre a bien été calculée, mais au moins une journée reste trop longue "
                f"({max(stage_distances):.1f} km pour une limite de {daily_max:.1f} km). "
                f"Meilleur secours: {route.get('routing_mode') or 'inconnu'}, "
                f"{float(route.get('distance') or 0):.1f} km au total."
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
    "_matrix_subloop_candidates",
    "_constraint_near_start",
    "_balanced_corridor_stays",
    "_route_points_with_stays",
    "_roundtrip_stage_distances",
]
