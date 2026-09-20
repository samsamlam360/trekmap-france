"""GR / hiking-route guidance for TrekBrain v9.

A named hiking relation is strong routing evidence, not a safety guarantee.
This layer discovers OSM hiking relations (GR/GRP and national/regional walking
networks), uses their actual member geometry as a corridor, prefers campsites
near that corridor, and adds corridor waypoints before the normal pedestrian
router runs. Final geometry is still accepted only by TrekBrain's routing safety
gate, so a relation never authorises a straight-line or water crossing fallback.
"""
from __future__ import annotations

from contextvars import ContextVar
import math
import re
import unicodedata
from typing import Any

_ACTIVE_TRAILS: ContextVar[list[dict[str, Any]]] = ContextVar("trekbrain_gr_trails", default=[])
_INSTALLED = False


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _dist(a: dict[str, Any] | list[float], b: dict[str, Any] | list[float]) -> float:
    if isinstance(a, dict):
        lat1, lon1 = float(a["lat"]), float(a["lon"])
    else:
        lat1, lon1 = float(a[0]), float(a[1])
    if isinstance(b, dict):
        lat2, lon2 = float(b["lat"]), float(b["lon"])
    else:
        lat2, lon2 = float(b[0]), float(b[1])
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _path_length(coords: list[list[float]]) -> float:
    return sum(_dist(a, b) for a, b in zip(coords, coords[1:]))


def _is_priority_relation(tags: dict[str, Any]) -> bool:
    ref = _fold(tags.get("ref") or "")
    name = _fold(tags.get("name") or "")
    network = _fold(tags.get("network") or "")
    return (
        bool(re.search(r"\bgr\s*\d|\bgrp\b", ref))
        or bool(re.search(r"\bgr\s*\d|\bgrp\b", name))
        or network in {"iwn", "nwn", "rwn"}
    )


def _member_geometry(member: dict[str, Any]) -> list[list[float]]:
    out = []
    for point in member.get("geometry") or []:
        lat, lon = _number(point.get("lat")), _number(point.get("lon"))
        if lat is None or lon is None:
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            row = [lat, lon]
            if not out or _dist(out[-1], row) > 0.002:
                out.append(row)
    return out


def _join_relation_members(members: list[dict[str, Any]]) -> list[list[float]]:
    components: list[list[list[float]]] = []
    current: list[list[float]] = []
    for member in members:
        if member.get("type") != "way":
            continue
        geom = _member_geometry(member)
        if len(geom) < 2:
            continue
        if not current:
            current = geom[:]
            continue
        d_first = _dist(current[-1], geom[0])
        d_last = _dist(current[-1], geom[-1])
        if min(d_first, d_last) <= 1.2:
            if d_last < d_first:
                geom.reverse()
            if _dist(current[-1], geom[0]) <= 0.03:
                current.extend(geom[1:])
            else:
                current.extend(geom)
        else:
            components.append(current)
            current = geom[:]
    if current:
        components.append(current)
    if not components:
        return []
    return max(components, key=_path_length)


def _downsample(coords: list[list[float]], max_points: int = 500) -> list[list[float]]:
    if len(coords) <= max_points:
        return coords
    stride = max(1, math.ceil(len(coords) / max_points))
    sampled = coords[::stride]
    if sampled[-1] != coords[-1]:
        sampled.append(coords[-1])
    return sampled


def _discover(v3, center: dict[str, Any], radius_km: float) -> list[dict[str, Any]]:
    radius_m = max(3000, min(int(max(radius_km, 12.0) * 1000), 45000))
    query = (
        "[out:json][timeout:20];("
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"=\"hiking\"][\"network\"~\"^(iwn|nwn|rwn)$\"];"
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"=\"hiking\"][\"ref\"~\"^(GR|GRP)\",i];"
        ");out geom tags 36;"
    )
    try:
        payload = v3._overpass(query)
    except Exception:
        return []
    trails = []
    seen = set()
    for element in payload.get("elements") or []:
        if element.get("type") != "relation":
            continue
        tags = element.get("tags") or {}
        if not _is_priority_relation(tags):
            continue
        coords = _join_relation_members(element.get("members") or [])
        if len(coords) < 8:
            continue
        length = _path_length(coords)
        if length < 4.0:
            continue
        ref = str(tags.get("ref") or "").strip()
        name = str(tags.get("name") or ref or "Itinéraire de randonnée").strip()
        identity = (element.get("id"), ref.casefold(), name.casefold())
        if identity in seen:
            continue
        seen.add(identity)
        trails.append({
            "id": element.get("id"),
            "name": name[:160],
            "ref": ref[:60],
            "network": str(tags.get("network") or "")[:20],
            "coords": _downsample(coords),
            "length_km": round(length, 1),
            "source_url": f"https://www.openstreetmap.org/relation/{element.get('id')}",
            "confidence": "high-route-evidence",
        })
    trails.sort(key=lambda t: (0 if _fold(t.get("ref")).startswith("gr") else 1, -t["length_km"]))
    return trails[:8]


def _nearest_index(point: dict[str, Any], trail: dict[str, Any]) -> tuple[int, float]:
    coords = trail.get("coords") or []
    if not coords:
        return 0, float("inf")
    best_i, best_d = 0, float("inf")
    stride = max(1, len(coords) // 350)
    for i in range(0, len(coords), stride):
        d = _dist(point, coords[i])
        if d < best_d:
            best_i, best_d = i, d
    lo, hi = max(0, best_i - stride), min(len(coords), best_i + stride + 1)
    for i in range(lo, hi):
        d = _dist(point, coords[i])
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def _cumulative(coords: list[list[float]]) -> list[float]:
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + _dist(a, b))
    return out


def _trail_proximity(item: dict[str, Any], trails: list[dict[str, Any]] | None = None) -> float:
    trails = trails if trails is not None else _ACTIVE_TRAILS.get()
    best = float("inf")
    for trail in trails:
        _, d = _nearest_index(item, trail)
        best = min(best, d)
    return best


def _trail_section(a: dict[str, Any], b: dict[str, Any], intent: dict[str, Any]) -> tuple[dict[str, Any] | None, list[list[float]]]:
    best = None
    for trail in _ACTIVE_TRAILS.get():
        ia, da = _nearest_index(a, trail)
        ib, db = _nearest_index(b, trail)
        if da > 4.2 or db > 4.2:
            continue
        coords = trail["coords"]
        if ia == ib:
            continue
        lo, hi = sorted((ia, ib))
        path = coords[lo:hi + 1]
        if ia > ib:
            path = list(reversed(path))
        length = _path_length(path)
        direct = max(0.1, _dist(a, b))
        max_reasonable = max(float(intent.get("daily_max") or 30) * 1.75, direct * 3.4 + 3.0)
        if length < 1.5 or length > max_reasonable:
            continue
        rank = da + db + max(0.0, length - float(intent.get("daily_target") or 18)) * 0.04
        if best is None or rank < best[0]:
            best = (rank, trail, path)
    return (best[1], best[2]) if best else (None, [])


def _anchors_for(a: dict[str, Any], b: dict[str, Any], intent: dict[str, Any], max_anchors: int = 3) -> list[dict[str, Any]]:
    trail, path = _trail_section(a, b, intent)
    if not trail or len(path) < 4:
        return []
    count = 2 if _path_length(path) >= 7 else 1
    count = min(max_anchors, count)
    anchors = []
    for n in range(1, count + 1):
        idx = round((len(path) - 1) * n / (count + 1))
        lat, lon = path[idx]
        anchors.append({
            "name": trail.get("ref") or trail.get("name") or "GR",
            "category": "trail",
            "lat": lat,
            "lon": lon,
            "source_url": trail.get("source_url"),
            "trail_name": trail.get("name"),
            "trail_ref": trail.get("ref"),
            "gr_guidance": True,
        })
    return anchors


def _trail_position(item: dict[str, Any], trail: dict[str, Any], cumulative: list[float]) -> tuple[float, float]:
    idx, distance = _nearest_index(item, trail)
    return cumulative[min(idx, len(cumulative) - 1)], distance


def gr_candidates(v3, start, end, items, intent, strategy: str) -> list[Any]:
    days = max(1, int(intent.get("days") or 1))
    if days <= 1 or not _ACTIVE_TRAILS.get():
        return []
    accommodation = intent.get("accommodation")
    if accommodation == "camping":
        stays = [x for x in items if x.get("category") == "camping"]
    elif accommodation == "refuge":
        stays = [x for x in items if x.get("category") == "refuge"]
    else:
        stays = [x for x in items if x.get("category") in {"camping", "refuge", "village"}]
    if len(stays) < days - 1:
        return []
    out = []
    target = float(intent.get("daily_target") or 18)
    for trail in _ACTIVE_TRAILS.get()[:5]:
        coords = trail.get("coords") or []
        if len(coords) < 4:
            continue
        cumulative = _cumulative(coords)
        start_pos, start_off = _trail_position(start, trail, cumulative)
        end_pos, end_off = _trail_position(end, trail, cumulative)
        if start_off > 5.0 or end_off > 5.0:
            continue
        stay_rows = []
        for stay in stays:
            pos, off = _trail_position(stay, trail, cumulative)
            if off <= 4.0:
                stay_rows.append((stay, pos, off))
        if len(stay_rows) < days - 1:
            continue
        for direction in (1, -1):
            chosen = []
            used = set()
            error = 0.0
            current = start
            for step in range(1, days):
                wanted = start_pos + direction * target * step
                ranked = []
                for stay, pos, off in stay_rows:
                    key = stay.get("source_url") or stay.get("name")
                    if key in used:
                        continue
                    along_error = abs(pos - wanted)
                    straight = _dist(current, stay)
                    if straight > float(intent.get("daily_max") or 30) * 1.25:
                        continue
                    ranked.append((along_error + off * 2.2 + abs(straight - target * 0.62) * 0.45, stay))
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
            out.append(v3.Candidate(boundaries, f"{strategy}-gr", error * 0.35 - 12.0))
    return sorted(out, key=lambda c: c.heuristic)[:4]


def clear_gr_context() -> None:
    _ACTIVE_TRAILS.set([])


def active_trail_summary() -> list[dict[str, Any]]:
    return [
        {k: trail.get(k) for k in ("name", "ref", "network", "length_km", "source_url", "confidence")}
        for trail in _ACTIVE_TRAILS.get()
    ]


def install_gr_guidance(v3) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_extra = v3._extra_nearby
    original_utility = v3._utility
    original_beam = v3._beam_candidates
    original_route_points = v3._route_points_for_candidate

    def extra_nearby(center, radius_km):
        items, notes = original_extra(center, radius_km)
        trails = _discover(v3, center, radius_km)
        _ACTIVE_TRAILS.set(trails)
        for trail in trails:
            coords = trail.get("coords") or []
            if not coords:
                continue
            lat, lon = coords[len(coords) // 2]
            items.append({
                "name": trail.get("ref") or trail.get("name") or "GR",
                "category": "trail",
                "lat": lat,
                "lon": lon,
                "source_url": trail.get("source_url"),
                "trail_name": trail.get("name"),
                "trail_ref": trail.get("ref"),
                "gr_guidance": True,
            })
        if trails:
            labels = [t.get("ref") or t.get("name") for t in trails[:3]]
            notes = list(notes or []) + [
                "Corridor(s) de randonnée OSM détecté(s) et utilisé(s) comme préférence de calcul : " + ", ".join(x for x in labels if x) + "."
            ]
        return items, notes

    def utility(item, intent, strategy):
        score = original_utility(item, intent, strategy)
        trails = _ACTIVE_TRAILS.get()
        if not trails:
            return score
        cat = item.get("category")
        proximity = _trail_proximity(item, trails)
        if cat == "trail":
            score += 7.0
        elif cat in {"camping", "refuge"}:
            if proximity <= 0.8:
                score += 8.0
            elif proximity <= 2.0:
                score += 5.0
            elif proximity <= 4.0:
                score += 2.0
        elif cat in {"village", "food", "water"} and proximity <= 1.5:
            score += 1.8
        return score

    def beam_candidates(start, end, center, items, intent, strategy, width=8):
        normal = list(original_beam(start, end, center, items, intent, strategy, width))
        guided = gr_candidates(v3, start, end, items, intent, strategy)
        combined = normal + guided
        combined.sort(key=lambda c: c.heuristic)
        return combined[: max(width, 8)]

    def route_points_for_candidate(candidate, all_items, intent, forced_via):
        points, highlights = original_route_points(candidate, all_items, intent, forced_via)
        # Matrix candidates were selected using real hiking-network distances.
        # Forcing extra GR anchors afterwards can change those carefully balanced
        # 20 km stages into 25+ km stages. Let ORS choose the best hiking path
        # directly between the selected overnight stops.
        if "matrix-loop" in str(getattr(candidate, "strategy", "")):
            return points, highlights
        if not _ACTIVE_TRAILS.get() or len(points) < 2:
            return points, highlights
        guided = [points[0]]
        inserted = 0
        for a, b in zip(points, points[1:]):
            for anchor in _anchors_for(a, b, intent, max_anchors=2):
                if inserted >= 14:
                    break
                if _dist(guided[-1], anchor) > 0.12 and _dist(anchor, b) > 0.12:
                    guided.append(anchor)
                    inserted += 1
            guided.append(b)
        return guided, highlights

    v3._extra_nearby = extra_nearby
    v3._utility = utility
    v3._beam_candidates = beam_candidates
    v3._route_points_for_candidate = route_points_for_candidate


__all__ = [
    "install_gr_guidance", "clear_gr_context", "active_trail_summary",
    "gr_candidates", "_join_relation_members", "_is_priority_relation",
]
