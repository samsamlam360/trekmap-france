"""Multi-trail / pedestrian-network loop planning for TrekBrain v9.

This layer fills the biggest gap left by the GR-only planner: a useful loop does
not need to be represented by one closed GR relation.  It can combine several
GR/GRP corridors, ordinary OSM walking paths (through ORS), and short campsite
branches.  Candidate generation stays cheap and deterministic; OpenRouteService
remains the authority for every final metre of pedestrian geometry.
"""
from __future__ import annotations

from contextvars import ContextVar
import math
from typing import Any

_INSTALLED = False
_EXTRA_STAYS: ContextVar[dict[str, list[dict[str, Any]]]] = ContextVar("trekbrain_network_stays", default={})


def _fold(v3, value: Any) -> str:
    return v3._fold(str(value or ""))


def _key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or f"{item.get('name')}:{item.get('lat')}:{item.get('lon')}")


def _bearing(center: dict[str, Any], point: dict[str, Any]) -> float:
    lat1 = math.radians(float(center["lat"]))
    lat2 = math.radians(float(point["lat"]))
    dlon = math.radians(float(point["lon"]) - float(center["lon"]))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.atan2(y, x) + 2 * math.pi) % (2 * math.pi)


def _local_xy(origin: dict[str, Any], point: dict[str, Any]) -> tuple[float, float]:
    lat0 = math.radians(float(origin["lat"]))
    x = (float(point["lon"]) - float(origin["lon"])) * 111.320 * math.cos(lat0)
    y = (float(point["lat"]) - float(origin["lat"])) * 110.574
    return x, y


def _shape_ratio(points: list[dict[str, Any]]) -> float:
    """Area / perimeter². Near zero means an out-and-back shaped polygon."""
    if len(points) < 4:
        return 0.0
    origin = points[0]
    xy = [_local_xy(origin, p) for p in points]
    if xy[-1] != xy[0]:
        xy.append(xy[0])
    area2 = 0.0
    perimeter = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
        area2 += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)
    area = abs(area2) / 2
    return area / max(perimeter * perimeter, 1e-6)


def _trail_bonus(item: dict[str, Any], gr) -> float:
    try:
        proximity = gr._trail_proximity(item)
    except Exception:
        return 0.0
    if proximity <= 0.8:
        return 2.2
    if proximity <= 2.0:
        return 1.3
    if proximity <= 3.2:
        return 0.5
    return 0.0


def _estimated_leg(a: dict[str, Any], b: dict[str, Any], intent: dict[str, Any], v3, gr) -> float:
    """Fast pre-ORS estimate. Final acceptance always uses real ORS distance."""
    direct = max(0.05, float(v3._dist(a, b)))
    best = direct * 1.20
    # When both points can be joined by one known hiking relation, use that
    # corridor length plus their branches as a better estimate.
    try:
        trail, path = gr._trail_section(a, b, intent)
        if trail and len(path) >= 2:
            ia, da = gr._nearest_index(a, trail)
            ib, db = gr._nearest_index(b, trail)
            corridor = gr._path_length(path) + da + db
            if 0.2 < corridor < best * 2.2:
                best = min(best * 1.35, corridor)
    except Exception:
        pass
    return best


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        k = _key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


def _expanded_stays(v3, center: dict[str, Any], items: list[dict[str, Any]], category: str, needed: int) -> list[dict[str, Any]]:
    current = [x for x in items if x.get("category") == category]
    # The broad OSM query is capped across all POI categories. A targeted query
    # prevents water/food/transit results from crowding campsites out.
    cache_key = f"{category}:{round(float(center['lat']),3)}:{round(float(center['lon']),3)}"
    cached = _EXTRA_STAYS.get().get(cache_key)
    if cached is None and len(current) < max(needed + 2, 5):
        try:
            fetched = v3._nearby(float(center["lat"]), float(center["lon"]), 30.0, [category])
        except Exception:
            fetched = []
        state = dict(_EXTRA_STAYS.get())
        state[cache_key] = fetched
        _EXTRA_STAYS.set(state)
        cached = fetched
    return _dedupe(current + list(cached or []))


def _candidate_sequences(v3, gr, start, center, stays, intent, width: int = 90):
    days = max(1, int(intent.get("days") or 1))
    nights = days - 1
    if nights <= 0 or len(stays) < nights:
        return []

    target = float(intent.get("daily_target") or 18)
    daily_min = float(intent.get("daily_min") or target * 0.85)
    daily_max = float(intent.get("daily_max") or target * 1.15)
    planning_max = daily_max + max(1.5, min(3.0, target * 0.12))
    total_target = float(intent.get("total_target") or target * days)
    radius_limit = min(36.0, max(14.0, target * 1.65))

    pool = []
    for stay in stays:
        radial = float(v3._dist(start, stay))
        if radial < 1.0 or radial > radius_limit:
            continue
        pool.append((stay, radial, _bearing(center, stay), _trail_bonus(stay, gr)))
    # Keep broad geographic coverage instead of only the closest campsites.
    pool.sort(key=lambda row: (row[1] - row[3] * 1.8, row[2]))
    pool = pool[:24]
    if len(pool) < nights:
        return []

    # State = cost, chosen, estimated stage distances, last point.
    beam = [(0.0, [], [], start)]
    for step in range(nights):
        expanded = []
        for cost, chosen, legs, last in beam:
            used = {_key(x) for x in chosen}
            for stay, radial, bearing, trail_bonus in pool:
                if _key(stay) in used:
                    continue
                leg = _estimated_leg(last, stay, intent, v3, gr)
                if leg > planning_max:
                    continue
                if step > 0 and leg < max(2.0, daily_min * 0.35):
                    continue
                # Encourage angular/geographic progression so three camps on
                # one road cannot masquerade as a loop.
                points = [start] + chosen + [stay]
                shape = _shape_ratio(points + [start]) if len(points) >= 3 else 0.0
                same_side_penalty = 0.0
                if chosen:
                    prev_b = _bearing(center, chosen[-1])
                    delta = abs((bearing - prev_b + math.pi) % (2 * math.pi) - math.pi)
                    if delta < math.radians(18):
                        same_side_penalty = 4.0
                leg_error = abs(leg - target)
                short_penalty = max(0.0, daily_min - leg) * 0.9
                expanded.append((
                    cost + leg_error * 1.05 + short_penalty + same_side_penalty - trail_bonus - shape * 18.0,
                    chosen + [stay], legs + [leg], stay,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:width]

    finals = []
    for cost, chosen, legs, last in beam:
        final_leg = _estimated_leg(last, start, intent, v3, gr)
        if final_leg > planning_max:
            continue
        all_legs = legs + [final_leg]
        polygon = [start] + chosen + [start]
        shape = _shape_ratio(polygon)
        # This threshold is intentionally permissive for elongated coastal
        # loops, but eliminates the near-zero area of classic out-and-back sets.
        if shape < 0.0022:
            continue
        total = sum(all_legs)
        worst = max(all_legs)
        spread = worst - min(all_legs)
        score = (
            cost
            + abs(final_leg - target) * 1.05
            + abs(total - total_target) * 0.38
            + spread * 0.32
            + max(0.0, worst - daily_max) * 5.0
            - shape * 120.0
        )
        finals.append((score, chosen, all_legs, shape, total))
    finals.sort(key=lambda row: row[0])
    return finals[:12]


def network_loop_candidates(v3, gr, start, center, items, intent, strategy: str):
    if _fold(v3, intent.get("route_type")) != "boucle":
        return []
    days = max(1, int(intent.get("days") or 1))
    if days <= 1:
        return []

    accommodation = intent.get("accommodation")
    if accommodation == "camping":
        category = "camping"
    elif accommodation == "refuge":
        category = "refuge"
    else:
        category = "camping"

    stays = _expanded_stays(v3, center, items, category, days - 1)
    solutions = _candidate_sequences(v3, gr, start, center, stays, intent)
    out = []
    for rank, (score, chosen, legs, shape, total) in enumerate(solutions[:8]):
        boundaries = [start] + chosen + [start]
        heuristic = score * 0.18 - 34.0 + rank * 0.25
        out.append(v3.Candidate(boundaries, f"{strategy}-path-network-loop", heuristic))
    return out


def install_path_network(v3, gr) -> None:
    """Add multi-corridor loop hypotheses after GR guidance/detours are installed."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_beam = v3._beam_candidates

    def beam_candidates(start, end, center, items, intent, strategy, width=8):
        normal = list(original_beam(start, end, center, items, intent, strategy, width))
        network = network_loop_candidates(v3, gr, start, center, items, intent, strategy)
        combined = normal + network
        combined.sort(key=lambda c: c.heuristic)
        seen = set()
        out = []
        for candidate in combined:
            signature = tuple((round(float(p.get("lat")), 5), round(float(p.get("lon")), 5)) for p in candidate.boundaries)
            if signature in seen:
                continue
            seen.add(signature)
            out.append(candidate)
            if len(out) >= max(12, width):
                break
        return out

    v3._beam_candidates = beam_candidates


__all__ = [
    "install_path_network", "network_loop_candidates", "_candidate_sequences",
    "_shape_ratio", "_estimated_leg",
]
