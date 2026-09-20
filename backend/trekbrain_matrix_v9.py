"""Matrix-first constraint planner for TrekBrain v9.

Architecture:
1. retrieve real candidate campsites/refuges from OSM;
2. ask ORS Matrix once for *real pedestrian distances* between them;
3. solve the multi-day loop as a constrained search on that matrix;
4. only then request detailed route geometry for the best few candidates.

This is deliberately not an LLM geometry generator. Language understanding may
suggest goals, but route feasibility is decided by the hiking graph.
"""
from __future__ import annotations

import math
from typing import Any

_INSTALLED = False


def _item_key(item: dict[str, Any]) -> str:
    return str(item.get("source_url") or f"{item.get('name')}:{item.get('lat')}:{item.get('lon')}")


def _shape_ratio(start: dict[str, Any], chosen: list[dict[str, Any]]) -> float:
    """Cheap geometric anti-out-and-back score based on campsite polygon area."""
    if len(chosen) < 2:
        return 0.0
    lat0 = math.radians(float(start["lat"]))

    def xy(p):
        return (
            (float(p["lon"]) - float(start["lon"])) * 111.320 * math.cos(lat0),
            (float(p["lat"]) - float(start["lat"])) * 110.574,
        )

    pts = [xy(start)] + [xy(x) for x in chosen] + [xy(start)]
    area2 = 0.0
    perimeter = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        area2 += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)
    return abs(area2) / 2 / max(perimeter * perimeter, 1e-6)


def _matrix_sequences(matrix, stays, intent, width: int = 160):
    """Choose all overnight stops simultaneously from a real distance matrix.

    Matrix index 0 is the departure; indexes 1..N are stays. Each accepted edge
    is therefore a network-routable hiking leg, not an aerial approximation.
    """
    days = max(1, int(intent.get("days") or 1))
    nights = days - 1
    if nights <= 0 or len(stays) < nights:
        return []
    if not matrix or len(matrix) != len(stays) + 1:
        return []

    target = float(intent.get("daily_target") or 18)
    daily_min = float(intent.get("daily_min") or target * 0.85)
    daily_max = float(intent.get("daily_max") or target * 1.15)
    total_target = float(intent.get("total_target") or target * days)
    hard_max = daily_max + 0.35

    # state = cost, indices, legs, last_index
    beam = [(0.0, [], [], 0)]
    for night in range(nights):
        expanded = []
        for cost, chosen, legs, last in beam:
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
                # Even before selecting future campsites, the current point must
                # still be capable of returning to the start within the number of
                # remaining hiking days. This prunes hopeless branches early.
                if back > remaining_days * hard_max + 0.5:
                    continue

                day_error = abs(leg - target)
                too_short = max(0.0, daily_min - leg)
                # Prefer points that leave useful room for the remaining days.
                expected_back = remaining_days * target
                future_error = abs(back - expected_back) * 0.12
                expanded.append((
                    cost + day_error * 1.6 + too_short * 1.1 + future_error,
                    chosen + [idx], legs + [leg], idx,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda row: row[0])
        beam = expanded[:width]

    finals = []
    for cost, chosen, legs, last in beam:
        final_leg = matrix[last][0]
        if final_leg is None:
            continue
        final_leg = float(final_leg)
        if final_leg <= 0.2 or final_leg > hard_max:
            continue
        all_legs = legs + [final_leg]
        selected = [stays[i - 1] for i in chosen]
        shape = _shape_ratio({"lat": stays[0].get("_start_lat", 0), "lon": stays[0].get("_start_lon", 0)}, selected) if stays and "_start_lat" in stays[0] else 0.0
        total = sum(all_legs)
        spread = max(all_legs) - min(all_legs)
        final_cost = (
            cost
            + abs(final_leg - target) * 1.6
            + abs(total - total_target) * 0.45
            + spread * 0.38
            + max(0.0, daily_min - final_leg) * 1.1
        )
        finals.append((final_cost, chosen, all_legs, total, shape))
    finals.sort(key=lambda row: row[0])
    return finals[:16]


def _select_stays(v3, network, start, center, items, intent):
    days = max(1, int(intent.get("days") or 1))
    accommodation = intent.get("accommodation")
    category = "refuge" if accommodation == "refuge" else "camping"
    stays = network._expanded_stays(v3, center, items, category, days - 1)
    target = float(intent.get("daily_target") or 18)
    radial_limit = min(38.0, max(12.0, target * 1.45))

    rows = []
    for item in stays:
        try:
            radial = float(v3._dist(start, item))
        except Exception:
            continue
        if radial < 1.0 or radial > radial_limit:
            continue
        row = dict(item)
        row["_start_lat"] = float(start["lat"])
        row["_start_lon"] = float(start["lon"])
        rows.append((radial, row))

    # Preserve both near and far candidates. A pure nearest-neighbour cut is bad
    # for loops because all campsites can end up on the same side of town.
    rows.sort(key=lambda x: x[0])
    if len(rows) <= 20:
        return [x[1] for x in rows]
    near = rows[:10]
    far = rows[-6:]
    middle = rows[10:-6]
    stride = max(1, len(middle) // 4)
    sampled = middle[::stride][:4]
    out = []
    seen = set()
    for _, item in near + sampled + far:
        k = _item_key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out[:20]


def matrix_loop_candidates(v3, ors, network, start, center, items, intent, strategy: str):
    if v3._fold(intent.get("route_type") or "") != "boucle":
        return []
    days = max(1, int(intent.get("days") or 1))
    if days <= 1:
        return []
    stays = _select_stays(v3, network, start, center, items, intent)
    if len(stays) < days - 1:
        return []

    coords = [[float(start["lat"]), float(start["lon"])]] + [
        [float(x["lat"]), float(x["lon"])] for x in stays
    ]
    result = ors.get_distance_matrix(coords)
    matrix = result.get("distances") if isinstance(result, dict) else None
    if not matrix:
        return []

    solutions = _matrix_sequences(matrix, stays, intent)
    out = []
    for rank, (cost, chosen, legs, total, _shape) in enumerate(solutions[:8]):
        selected = [stays[i - 1] for i in chosen]
        # Now that the start is available, apply the real polygon shape filter.
        shape = _shape_ratio(start, selected)
        if days >= 3 and shape < 0.0015:
            continue
        boundaries = [start] + selected + [start]
        heuristic = cost * 0.20 - 55.0 + rank * 0.2 - min(shape * 120.0, 4.0)
        out.append(v3.Candidate(boundaries, f"{strategy}-matrix-loop", heuristic))
    return out


def install_matrix_planner(v3, ors, network) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_beam = v3._beam_candidates

    def beam_candidates(start, end, center, items, intent, strategy, width=8):
        # Matrix candidates are generated first because they already know the
        # real walking distance between every overnight stop. Generic/GR logic
        # remains as a resilient fallback if the Matrix endpoint is unavailable.
        matrix_rows = matrix_loop_candidates(v3, ors, network, start, center, items, intent, strategy)
        normal = list(original_beam(start, end, center, items, intent, strategy, width))
        combined = matrix_rows + normal
        combined.sort(key=lambda c: c.heuristic)
        seen, out = set(), []
        for candidate in combined:
            sig = tuple((round(float(p["lat"]), 5), round(float(p["lon"]), 5)) for p in candidate.boundaries)
            if sig in seen:
                continue
            seen.add(sig)
            out.append(candidate)
            if len(out) >= max(12, width):
                break
        return out

    v3._beam_candidates = beam_candidates


__all__ = ["install_matrix_planner", "matrix_loop_candidates", "_matrix_sequences", "_shape_ratio"]
