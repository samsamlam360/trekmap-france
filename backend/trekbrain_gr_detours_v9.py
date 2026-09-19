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
        total_target = float(intent.get("total_target") or target * days)
        generated = []
        loop_requested = v3_module._fold(intent.get("route_type") or "") in {"boucle", "aller-retour", "aller retour"}

        for trail in gr._ACTIVE_TRAILS.get()[:6]:
            coords = trail.get("coords") or []
            if len(coords) < 4:
                continue
            cum = gr._cumulative(coords)
            length = cum[-1]
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

            closed = _is_loop(trail, gr)
            for direction in (1, -1):
                chosen = []
                used = set()
                error = 0.0
                current = start
                for step in range(1, days):
                    ranked = []
                    if loop_requested and closed:
                        wanted_progress = length * step / days
                    else:
                        wanted_progress = target * step

                    for stay, pos, off in rows:
                        key = stay.get("source_url") or stay.get("name")
                        if key in used:
                            continue
                        progress = directed_progress(pos, start_pos, length, direction) if closed else direction * (pos - start_pos)
                        if progress <= 0:
                            continue
                        along_error = abs(progress - wanted_progress)
                        straight = gr._dist(current, stay)
                        if straight > float(intent.get("daily_max") or 30) * 1.30:
                            continue
                        # Off-corridor distance is a real detour, not a reason to
                        # reject the campsite. Around 2 km is perfectly normal.
                        cost = along_error + off * 1.25 + abs(straight - target * 0.65) * 0.35
                        ranked.append((cost, stay))
                    if not ranked:
                        chosen = []
                        break
                    cost, stay = min(ranked, key=lambda row: row[0])
                    chosen.append(stay)
                    used.add(stay.get("source_url") or stay.get("name"))
                    error += cost
                    current = stay

                if len(chosen) != days - 1:
                    continue
                boundaries = [start] + chosen + [end]
                # Prefer GR-backed hypotheses enough to survive the generic beam
                # ranking, but leave final distance/scoring to the real route.
                loop_penalty = abs(length - total_target) * 0.05 if loop_requested and closed else 0.0
                generated.append(v3_module.Candidate(boundaries, f"{strategy}-gr-detour", error * 0.22 + loop_penalty - 22.0))

        combined = existing + generated
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
        return unique[:8]

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
