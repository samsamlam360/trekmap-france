"""GR campsite-detour improvements for TrekBrain v9.

Real multi-day hiking rarely sleeps exactly on the painted trail. This layer
keeps the GR/GRP as the main corridor, but allows a short walking branch to a
real campsite and back to the corridor. It also prevents the generic planner
from silently using a village or scenic POI as an overnight stop when the user
explicitly asked for camping.
"""
from __future__ import annotations

import math
from typing import Any

CAMP_CORRIDOR_KM = 2.6
REFUGE_CORRIDOR_KM = 3.0
MAX_BRANCH_KM = 3.2
_INSTALLED = False


def _same_trail(a: dict[str, Any], b: dict[str, Any]) -> bool:
    aref = str(a.get("trail_ref") or "").strip().casefold()
    bref = str(b.get("trail_ref") or "").strip().casefold()
    aname = str(a.get("trail_name") or "").strip().casefold()
    bname = str(b.get("trail_name") or "").strip().casefold()
    return bool((aref and aref == bref) or (not aref and not bref and aname and aname == bname))


def _is_loop(trail, gr) -> bool:
    coords = trail.get("coords") or []
    return len(coords) >= 4 and gr._dist(coords[0], coords[-1]) <= 0.55


def _path_continuous(path, gr, max_gap_km: float = 0.30) -> bool:
    return bool(path) and all(gr._dist(a, b) <= max_gap_km for a, b in zip(path, path[1:]))


def _forward_arc(coords, ia: int, ib: int):
    if ia <= ib:
        return coords[ia:ib + 1]
    return coords[ia:] + coords[:ib + 1]


def _best_arc(trail, ia: int, ib: int, target_km: float, max_km: float, gr):
    coords = trail.get("coords") or []
    if not coords or ia == ib:
        return []
    if not _is_loop(trail, gr):
        lo, hi = sorted((ia, ib))
        path = coords[lo:hi + 1]
        return list(reversed(path)) if ia > ib else path

    forward = _forward_arc(coords, ia, ib)
    backward = list(reversed(_forward_arc(coords, ib, ia)))
    options = []
    for path in (forward, backward):
        if len(path) < 2 or not _path_continuous(path, gr):
            continue
        length = gr._path_length(path)
        if length <= max_km:
            options.append((abs(length - target_km), length, path))
    if not options:
        return []
    return min(options, key=lambda row: (row[0], row[1]))[2]



def _global_loop_sequences(trail, start, rows, intent, gr, direction: int, beam_width: int = 64):
    """Jointly optimise loop direction, overnight stops and every day's mileage."""
    days = max(1, int(intent.get("days") or 1))
    if days <= 1 or not _is_loop(trail, gr):
        return []
    coords = trail.get("coords") or []
    cum = gr._cumulative(coords)
    length = cum[-1]
    if length <= 0:
        return []
    start_pos, start_off = gr._trail_position(start, trail, cum)
    target = float(intent.get("daily_target") or 18)
    daily_min = float(intent.get("daily_min") or target * 0.75)
    daily_max = float(intent.get("daily_max") or target * 1.25)
    hard_max = daily_max + 0.35

    ordered = []
    for stay, pos, off in rows:
        progress = (pos - start_pos) % length if direction > 0 else (start_pos - pos) % length
        if 0.15 < progress < length - 0.15:
            ordered.append((progress, stay, off))
    ordered.sort(key=lambda row: row[0])
    if len(ordered) < days - 1:
        return []

    beam = [(0.0, [], 0.0, start_off)]
    for night in range(1, days):
        wanted = length * night / days
        expanded = []
        for cost, chosen, prev_progress, prev_off in beam:
            used = {x[1].get("source_url") or x[1].get("name") for x in chosen}
            for progress, stay, off in ordered:
                key = stay.get("source_url") or stay.get("name")
                if key in used or progress <= prev_progress + 0.15:
                    continue
                remaining_nights = (days - 1) - night
                if sum(1 for p, _, _ in ordered if p > progress + 0.15) < remaining_nights:
                    continue
                estimated_day = (progress - prev_progress) + prev_off + off
                if estimated_day > hard_max:
                    continue
                expanded.append((
                    cost + abs(estimated_day - target) * 1.35
                    + max(0.0, daily_min - estimated_day) * 1.8
                    + abs(progress - wanted) * 0.18 + off * 0.22,
                    chosen + [(progress, stay, off)], progress, off,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:beam_width]

    finals = []
    for cost, chosen, prev_progress, prev_off in beam:
        final_day = (length - prev_progress) + prev_off + start_off
        if final_day > hard_max:
            continue
        legs, last_progress, last_off = [], 0.0, start_off
        for progress, _, off in chosen:
            legs.append((progress - last_progress) + last_off + off)
            last_progress, last_off = progress, off
        legs.append((length - last_progress) + last_off + start_off)
        total = sum(legs)
        total_target = float(intent.get("total_target") or target * days)
        final_cost = cost + abs(final_day - target) * 1.35 + abs(total - total_target) * 0.30
        finals.append((final_cost, [row[1] for row in chosen], legs, total, direction))
    finals.sort(key=lambda row: row[0])
    return finals[:6]


def _global_linear_sequences(trail, start, end, rows, intent, gr, direction: int, beam_width: int = 64):
    """Joint optimiser for non-loop itineraries using monotonic GR progress."""
    days = max(1, int(intent.get("days") or 1))
    if days <= 1:
        return []
    coords = trail.get("coords") or []
    cum = gr._cumulative(coords)
    start_pos, start_off = gr._trail_position(start, trail, cum)
    end_pos, end_off = gr._trail_position(end, trail, cum)
    target = float(intent.get("daily_target") or 18)
    daily_min = float(intent.get("daily_min") or target * 0.75)
    daily_max = float(intent.get("daily_max") or target * 1.25)
    hard_max = max(daily_max, target * 1.22) + 0.35

    def progress(pos):
        return direction * (pos - start_pos)

    end_progress = progress(end_pos)
    if end_progress <= 0.5:
        return []
    ordered = sorted(
        [(progress(pos), stay, off) for stay, pos, off in rows if 0.15 < progress(pos) < end_progress - 0.15],
        key=lambda row: row[0],
    )
    if len(ordered) < days - 1:
        return []

    beam = [(0.0, [], 0.0, start_off)]
    for night in range(1, days):
        wanted = end_progress * night / days
        expanded = []
        for cost, chosen, prev_progress, prev_off in beam:
            used = {x[1].get("source_url") or x[1].get("name") for x in chosen}
            for prog, stay, off in ordered:
                key = stay.get("source_url") or stay.get("name")
                if key in used or prog <= prev_progress + 0.15:
                    continue
                if sum(1 for p, _, _ in ordered if p > prog + 0.15) < (days - 1 - night):
                    continue
                estimated_day = (prog - prev_progress) + prev_off + off
                if estimated_day > hard_max:
                    continue
                expanded.append((
                    cost + abs(estimated_day - target) * 1.35
                    + max(0.0, daily_min - estimated_day) * 1.8
                    + abs(prog - wanted) * 0.18 + off * 0.22,
                    chosen + [(prog, stay, off)], prog, off,
                ))
        if not expanded:
            return []
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:beam_width]

    finals = []
    for cost, chosen, prev_progress, prev_off in beam:
        final_day = (end_progress - prev_progress) + prev_off + end_off
        if final_day > hard_max:
            continue
        legs, lp, lo = [], 0.0, start_off
        for prog, _, off in chosen:
            legs.append((prog - lp) + lo + off)
            lp, lo = prog, off
        legs.append((end_progress - lp) + lo + end_off)
        total = sum(legs)
        total_target = float(intent.get("total_target") or target * days)
        finals.append((
            cost + abs(final_day - target) * 1.35 + abs(total - total_target) * 0.30,
            [row[1] for row in chosen], legs, total, direction,
        ))
    finals.sort(key=lambda row: row[0])
    return finals[:6]


def install_gr_detours(v3, gr) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_night_pool = v3._night_pool
    original_candidates = gr.gr_candidates

    def strict_night_pool(items, intent):
        accommodation = intent.get("accommodation")
        sleep = bool(intent.get("sleep"))
        days = max(1, int(intent.get("days") or 1))
        if not sleep or accommodation not in {"camping", "refuge"}:
            return original_night_pool(items, intent)

        category = "camping" if accommodation == "camping" else "refuge"
        preferred = [x for x in items if x.get("category") == category]
        if not preferred:
            return []

        limit = CAMP_CORRIDOR_KM if category == "camping" else REFUGE_CORRIDOR_KM
        near_corridor = [x for x in preferred if gr._trail_proximity(x) <= limit]
        # If enough genuine overnight places exist near a GR corridor, do not
        # pollute the candidate pool with villages, food POIs or viewpoints.
        if len(near_corridor) >= max(1, days - 1):
            return near_corridor
        return preferred

    def trail_section(a, b, intent):
        best = None
        target = float(intent.get("daily_target") or 18)
        max_day = float(intent.get("daily_max") or 30)
        for trail in gr._ACTIVE_TRAILS.get():
            ia, da = gr._nearest_index(a, trail)
            ib, db = gr._nearest_index(b, trail)
            # Start/end can be slightly farther from the GR; actual walking
            # connectors remain delegated to ORS.
            if da > MAX_BRANCH_KM or db > MAX_BRANCH_KM:
                continue
            path = _best_arc(trail, ia, ib, target, max(max_day * 1.9, target * 1.8), gr)
            if len(path) < 2 or not _path_continuous(path, gr):
                continue
            length = gr._path_length(path)
            direct = max(0.1, gr._dist(a, b))
            if length < 0.25 or length > max(max_day * 1.9, direct * 3.8 + 4.0):
                continue
            rank = da * 2.4 + db * 2.4 + abs(length - target) * 0.10
            if best is None or rank < best[0]:
                best = (rank, trail, path)
        return (best[1], best[2]) if best else (None, [])

    def anchor_for(trail, point, label: str):
        return {
            "name": label,
            "category": "trail",
            "lat": float(point[0]),
            "lon": float(point[1]),
            "source_url": trail.get("source_url"),
            "trail_name": trail.get("name"),
            "trail_ref": trail.get("ref"),
            "gr_guidance": True,
        }

    def anchors_for(a, b, intent, max_anchors=3):
        trail, path = gr._trail_section(a, b, intent)
        if not trail or len(path) < 2:
            return []

        anchors = []
        label = trail.get("ref") or trail.get("name") or "GR"
        # Explicit junctions are the key change: go from the campsite to its
        # nearest GR point, follow the GR, then branch to the next campsite.
        if gr._dist(a, path[0]) > 0.08:
            anchors.append(anchor_for(trail, path[0], f"{label} · jonction nuitée"))

        path_km = gr._path_length(path)
        middle_count = 2 if path_km >= 9 else 1 if path_km >= 3 else 0
        middle_count = min(middle_count, max_anchors)
        for n in range(1, middle_count + 1):
            idx = round((len(path) - 1) * n / (middle_count + 1))
            anchors.append(anchor_for(trail, path[idx], label))

        if gr._dist(b, path[-1]) > 0.08:
            anchors.append(anchor_for(trail, path[-1], f"{label} · jonction nuitée"))

        deduped = []
        for item in anchors:
            if not deduped or gr._dist(deduped[-1], item) > 0.06:
                deduped.append(item)
        # Junctions do not count against scenic-anchor budget. Still cap the
        # total to avoid unreasonable ORS waypoint counts.
        return deduped[: max(5, max_anchors + 2)]

    def directed_progress(pos: float, start_pos: float, length: float, direction: int) -> float:
        return (pos - start_pos) % length if direction > 0 else (start_pos - pos) % length

    def detour_candidates(v3_module, start, end, items, intent, strategy):
        existing = list(original_candidates(v3_module, start, end, items, intent, strategy))
        days = max(1, int(intent.get("days") or 1))
        accommodation = intent.get("accommodation")
        if days <= 1 or accommodation not in {"camping", "refuge"}:
            return existing

        category = "camping" if accommodation == "camping" else "refuge"
        limit = CAMP_CORRIDOR_KM if category == "camping" else REFUGE_CORRIDOR_KM
        stays = [x for x in items if x.get("category") == category]
        if len(stays) < days - 1:
            return existing

        target = float(intent.get("daily_target") or 18)
        generated = []
        loop_requested = v3_module._fold(intent.get("route_type") or "") == "boucle"

        for trail in gr._ACTIVE_TRAILS.get()[:6]:
            coords = trail.get("coords") or []
            if len(coords) < 4:
                continue
            cum = gr._cumulative(coords)
            start_pos, start_off = gr._trail_position(start, trail, cum)
            if start_off > MAX_BRANCH_KM:
                continue

            rows = []
            for stay in stays:
                pos, off = gr._trail_position(stay, trail, cum)
                if off <= limit:
                    rows.append((stay, pos, off))
            if len(rows) < days - 1:
                continue

            solutions = []
            if loop_requested:
                if not _is_loop(trail, gr):
                    continue
                for direction in (1, -1):
                    solutions.extend(_global_loop_sequences(trail, start, rows, intent, gr, direction))
            else:
                for direction in (1, -1):
                    solutions.extend(_global_linear_sequences(trail, start, end, rows, intent, gr, direction))

            for global_cost, chosen, estimated_legs, estimated_total, direction in sorted(solutions, key=lambda row: row[0])[:6]:
                boundaries = [start] + chosen + ([start] if loop_requested else [end])
                spread = max(estimated_legs) - min(estimated_legs) if estimated_legs else target
                heuristic = global_cost * 0.16 + spread * 0.12 - 28.0
                generated.append(v3_module.Candidate(
                    boundaries,
                    f"{strategy}-gr-global-{'cw' if direction > 0 else 'ccw'}",
                    heuristic,
                ))

        combined = generated + existing
        seen = set()
        unique = []
        for candidate in sorted(combined, key=lambda c: c.heuristic):
            key = tuple(
                (round(float(p.get("lat")), 5), round(float(p.get("lon")), 5))
                for p in candidate.boundaries
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique[:10]

    v3._night_pool = strict_night_pool
    gr._trail_section = trail_section
    gr._anchors_for = anchors_for
    gr.gr_candidates = detour_candidates


__all__ = [
    "install_gr_detours",
    "CAMP_CORRIDOR_KM",
    "REFUGE_CORRIDOR_KM",
    "MAX_BRANCH_KM",
]
