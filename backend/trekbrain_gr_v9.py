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
import json
import math
import re
import time
import unicodedata
from typing import Any

import requests

_ACTIVE_TRAILS: ContextVar[list[dict[str, Any]]] = ContextVar("trekbrain_gr_trails", default=[])
_INSTALLED = False

_WAYMARKED_BASE = "https://hiking.waymarkedtrails.org/api/v1"
_WAYMARKED_LIST_TIMEOUT_S = 2.4
_WAYMARKED_SEGMENTS_TIMEOUT_S = 3.0
_WAYMARKED_CACHE_TTL_S = 1800
_WAYMARKED_CACHE: dict[tuple[float, float, int], tuple[float, list[dict[str, Any]]]] = {}
_WAYMARKED_DETAIL_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_MERCATOR_R = 6378137.0


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
    """Return whether a hiking relation is useful route evidence.

    v9 used to keep only GR/GRP or high-level networks. That made the planner
    excellent on routes we had already encountered, but blind to established
    named itineraries such as many local/regional tours. A general planner must
    consider any identified hiking relation, then rank it instead of hard-coding
    its name.
    """
    ref = str(tags.get("ref") or "").strip()
    name = str(tags.get("name") or tags.get("local_name") or "").strip()
    network = _fold(tags.get("network") or "")
    route = _fold(tags.get("route") or "hiking")
    if route and route not in {"hiking", "foot", "walking"}:
        return False
    if network in {"iwn", "nwn", "rwn", "lwn"}:
        return True
    return bool(ref or name)


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


def _lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    x = _MERCATOR_R * math.radians(float(lon))
    y = _MERCATOR_R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _mercator_to_latlon(x: float, y: float) -> list[float]:
    lon = math.degrees(float(x) / _MERCATOR_R)
    lat = math.degrees(2 * math.atan(math.exp(float(y) / _MERCATOR_R)) - math.pi / 2)
    return [lat, lon]


def _waymarked_bbox(center: dict[str, Any], radius_km: float) -> str:
    lat = float(center["lat"])
    lon = float(center["lon"])
    radius = max(8.0, min(float(radius_km), 45.0))
    lat_pad = radius / 111.0
    cos_lat = max(0.15, abs(math.cos(math.radians(lat))))
    lon_pad = radius / (111.0 * cos_lat)
    minx, miny = _lonlat_to_mercator(lon - lon_pad, lat - lat_pad)
    maxx, maxy = _lonlat_to_mercator(lon + lon_pad, lat + lat_pad)
    return f"{minx:.1f},{miny:.1f},{maxx:.1f},{maxy:.1f}"


def _waymarked_request(
    path: str,
    params: dict[str, Any],
    timeout_s: float,
    *,
    retry: bool = True,
) -> dict[str, Any]:
    """Fetch Waymarked once, with one short retry for transient network/5xx failures.

    Crozon production runs showed that a single cold Waymarked miss can collapse
    an otherwise excellent GR 34 loop to the generic ORS fallback. The retry is
    deliberately narrow: no retry for ordinary 4xx responses, and the second
    socket budget is shorter than the first.
    """
    headers = {
        "Accept": "application/json",
        "Accept-Language": "fr",
        "User-Agent": "TrekMap-France/9.0 (+https://trekmap-france.onrender.com)",
    }
    first_timeout = max(0.8, float(timeout_s))
    retry_timeout = max(0.9, min(1.6, first_timeout * 0.55))
    timeouts = (first_timeout, retry_timeout) if retry else (first_timeout,)
    last_error = None

    for attempt, request_timeout in enumerate(timeouts, start=1):
        try:
            response = requests.get(
                _WAYMARKED_BASE + path,
                params=params,
                headers=headers,
                timeout=request_timeout,
            )
            status = int(getattr(response, "status_code", 200) or 200)
            if status >= 500:
                last_error = RuntimeError(f"Waymarked Trails HTTP {status}")
                if attempt < len(timeouts):
                    print(
                        f"[TrekBrain v9][waymarked] retry path={path} "
                        f"reason=http-{status} timeout_s={retry_timeout:.2f}",
                        flush=True,
                    )
                    continue
                raise last_error
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < len(timeouts):
                print(
                    f"[TrekBrain v9][waymarked] retry path={path} "
                    f"reason={exc.__class__.__name__} timeout_s={retry_timeout:.2f}",
                    flush=True,
                )
                continue
            raise

    if last_error is not None:
        raise last_error
    return {}


def _waymarked_lines(geometry: Any) -> list[list[list[float]]]:
    """Return WGS84 [lat, lon] lines from Waymarked EPSG:3857 GeoJSON."""
    if not isinstance(geometry, dict):
        return []
    kind = str(geometry.get("type") or "")
    coords = geometry.get("coordinates")
    raw_lines = []
    if kind == "LineString" and isinstance(coords, list):
        raw_lines = [coords]
    elif kind == "MultiLineString" and isinstance(coords, list):
        raw_lines = coords
    else:
        return []

    lines = []
    for raw in raw_lines:
        line = []
        for point in raw or []:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            x, y = _number(point[0]), _number(point[1])
            if x is None or y is None:
                continue
            row = _mercator_to_latlon(x, y)
            if not line or _dist(line[-1], row) > 0.002:
                line.append(row)
        if len(line) >= 2:
            lines.append(line)
    return lines


def _join_waymarked_lines(lines: list[list[list[float]]], max_gap_km: float = 1.6) -> list[list[float]]:
    """Greedily assemble clipped relation pieces and keep the longest component."""
    pending = [[list(p) for p in line] for line in lines if len(line) >= 2]
    components = []
    while pending:
        current = pending.pop(0)
        while pending:
            best = None
            for idx, line in enumerate(pending):
                options = (
                    (_dist(current[-1], line[0]), "append", False),
                    (_dist(current[-1], line[-1]), "append", True),
                    (_dist(current[0], line[-1]), "prepend", False),
                    (_dist(current[0], line[0]), "prepend", True),
                )
                distance, side, reverse = min(options, key=lambda row: row[0])
                if best is None or distance < best[0]:
                    best = (distance, idx, side, reverse)
            if best is None or best[0] > max_gap_km:
                break
            _distance, idx, side, reverse = best
            line = pending.pop(idx)
            if reverse:
                line.reverse()
            if side == "append":
                if _dist(current[-1], line[0]) <= 0.03:
                    current.extend(line[1:])
                else:
                    current.extend(line)
            else:
                if _dist(line[-1], current[0]) <= 0.03:
                    current = line[:-1] + current
                else:
                    current = line + current
        components.append(current)
    return max(components, key=_path_length) if components else []


def _waymarked_trails_from_payloads(
    routes_payload: dict[str, Any],
    segments_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    routes = {}
    for item in routes_payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        try:
            relation_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        ref = str(item.get("ref") or "").strip()
        name = str(item.get("name") or item.get("local_name") or ref or "").strip()
        if not _is_priority_relation({"ref": ref, "name": name, "network": "", "route": "hiking"}):
            continue
        routes[relation_id] = item
    if not routes:
        return []

    lines_by_id: dict[int, list[list[list[float]]]] = {relation_id: [] for relation_id in routes}
    for feature in segments_payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        try:
            relation_id = int(feature.get("id"))
        except (TypeError, ValueError):
            continue
        if relation_id not in routes:
            continue
        lines_by_id[relation_id].extend(_waymarked_lines(feature.get("geometry")))

    trails = []
    for relation_id, item in routes.items():
        coords = _join_waymarked_lines(lines_by_id.get(relation_id) or [])
        if len(coords) < 8:
            continue
        length = _path_length(coords)
        if length < 4.0:
            continue
        ref = str(item.get("ref") or "").strip()
        name = str(item.get("name") or item.get("local_name") or ref or "Itinéraire de randonnée").strip()
        trails.append({
            "id": relation_id,
            "name": name[:160],
            "ref": ref[:60],
            "network": "",
            "coords": _downsample(coords),
            "length_km": round(length, 1),
            "source_url": f"https://www.openstreetmap.org/relation/{relation_id}",
            "confidence": "high-route-evidence-secondary",
            "discovery_provider": "Waymarked Trails (OpenStreetMap-derived)",
        })
    trails.sort(key=lambda t: (
        0 if _fold(t.get("network")) in {"iwn", "nwn", "rwn"} else 1,
        0 if _fold(t.get("ref")).startswith("gr") else 1,
        -t["length_km"],
    ))
    return trails[:12]



def _waymarked_route_lines(route: Any) -> list[list[list[float]]]:
    """Extract ordered WGS84 lines from Waymarked's full route tree.

    The detail endpoint exposes the server-side route-builder representation,
    whose BaseWay geometries are Web-Mercator LineStrings. Appendices are not
    part of the primary itinerary. For split sections, the forward branch is
    the canonical direction of the route.
    """
    if isinstance(route, str):
        try:
            route = json.loads(route)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(route, dict):
        return []

    kind = str(route.get("route_type") or "")
    if kind == "base":
        geometry = route.get("geometry")
        return _waymarked_lines(geometry) if isinstance(geometry, dict) else []

    if kind == "linear":
        rows = []
        for way in route.get("ways") or []:
            rows.extend(_waymarked_route_lines(way))
        return rows

    if kind == "route":
        rows = []
        for segment in route.get("main") or []:
            rows.extend(_waymarked_route_lines(segment))
        return rows

    if kind == "split":
        rows = []
        branch = route.get("forward") or route.get("backward") or []
        for segment in branch:
            rows.extend(_waymarked_route_lines(segment))
        return rows

    # Appendix geometry intentionally stays out of the backbone: approaches and
    # alternatives may be useful map context but must not inflate the trek.
    return []


def _join_ordered_waymarked_lines(
    lines: list[list[list[float]]],
    max_gap_km: float = 1.6,
) -> list[list[float]]:
    """Join the provider's already ordered route tree without global reordering."""
    components: list[list[list[float]]] = []
    current: list[list[float]] = []
    for raw in lines or []:
        line = [list(point) for point in raw if isinstance(point, (list, tuple)) and len(point) >= 2]
        if len(line) < 2:
            continue
        if not current:
            current = line
            continue

        first_gap = _dist(current[-1], line[0])
        last_gap = _dist(current[-1], line[-1])
        if last_gap < first_gap:
            line.reverse()
            first_gap = last_gap

        if first_gap <= max_gap_km:
            if _dist(current[-1], line[0]) <= 0.03:
                current.extend(line[1:])
            else:
                current.extend(line)
        else:
            components.append(current)
            current = line

    if current:
        components.append(current)
    return max(components, key=_path_length) if components else []


def _hydrate_waymarked_relation(trail: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch one full Waymarked relation after clipped bbox evidence proved weak.

    This is a bounded rescue, not normal discovery. The caller limits it to the
    best one or two candidates, so unseen long treks gain authoritative route
    geometry without turning every request into another provider wave.
    """
    try:
        relation_id = int(trail.get("id"))
    except (TypeError, ValueError):
        return None
    if relation_id <= 0:
        return None

    now = time.monotonic()
    cached = _WAYMARKED_DETAIL_CACHE.get(relation_id)
    if cached and now - cached[0] < _WAYMARKED_CACHE_TTL_S:
        return {
            **cached[1],
            "coords": [list(point) for point in (cached[1].get("coords") or [])],
        }

    try:
        payload = _waymarked_request(
            f"/details/relation/{relation_id}",
            {},
            max(_WAYMARKED_SEGMENTS_TIMEOUT_S, 3.0),
        )
    except Exception:
        return None

    lines = _waymarked_route_lines(payload.get("route"))
    coords = _join_ordered_waymarked_lines(lines)
    if len(coords) < 8:
        return None
    length = _path_length(coords)
    if not math.isfinite(length) or length < 4.0:
        return None

    full = {
        **trail,
        "name": str(payload.get("name") or trail.get("name") or "Itinéraire de randonnée")[:160],
        "ref": str(payload.get("ref") or trail.get("ref") or "")[:60],
        "network": str(payload.get("group") or trail.get("network") or "")[:20],
        "coords": _downsample(coords),
        "length_km": round(length, 1),
        "source_url": trail.get("source_url") or f"https://www.openstreetmap.org/relation/{relation_id}",
        "confidence": "high-route-evidence-secondary-full",
        "discovery_provider": "Waymarked Trails full relation (OpenStreetMap-derived)",
    }
    _WAYMARKED_DETAIL_CACHE[relation_id] = (
        now,
        {**full, "coords": [list(point) for point in full["coords"]]},
    )
    while len(_WAYMARKED_DETAIL_CACHE) > 32:
        _WAYMARKED_DETAIL_CACHE.pop(next(iter(_WAYMARKED_DETAIL_CACHE)))
    return full


def _discover_waymarked(center: dict[str, Any], radius_km: float) -> list[dict[str, Any]]:
    """Bounded secondary discovery for explicit trail/coastal rescue only.

    Waymarked Trails indexes OpenStreetMap route relations and can return route
    geometry clipped to a local bbox. It is deliberately not called by the
    normal planner path; the coastal rescue invokes it only after Overpass has
    returned no usable hiking relation.
    """
    radius = max(12.0, min(float(radius_km), 45.0))
    key = (round(float(center["lat"]), 3), round(float(center["lon"]), 3), int(round(radius)))
    cached = _WAYMARKED_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _WAYMARKED_CACHE_TTL_S:
        return [
            {**trail, "coords": [list(p) for p in (trail.get("coords") or [])]}
            for trail in cached[1]
        ]

    bbox = _waymarked_bbox(center, radius)
    try:
        routes_payload = _waymarked_request(
            "/list/by_area",
            {"bbox": bbox, "limit": 20},
            _WAYMARKED_LIST_TIMEOUT_S,
            retry=False,
        )
    except Exception:
        return []

    priority = []
    seen = set()
    for item in routes_payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        try:
            relation_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        ref = str(item.get("ref") or "").strip()
        name = str(item.get("name") or item.get("local_name") or "").strip()
        if relation_id in seen or not _is_priority_relation({"ref": ref, "name": name, "network": "", "route": "hiking"}):
            continue
        seen.add(relation_id)
        priority.append(item)
    priority.sort(key=lambda item: (
        0 if _fold(item.get("ref") or "").startswith("gr") else 1,
        0 if "gr" in _fold(item.get("name") or "") else 1,
    ))
    priority = priority[:6]
    if not priority:
        return []

    relation_ids = [int(item["id"]) for item in priority]
    try:
        segments_payload = _waymarked_request(
            "/list/segments",
            {"bbox": bbox, "relations": ",".join(str(x) for x in relation_ids)},
            _WAYMARKED_SEGMENTS_TIMEOUT_S,
            retry=False,
        )
    except Exception:
        return []

    trails = _waymarked_trails_from_payloads(
        {"results": priority},
        segments_payload,
    )
    if trails:
        _WAYMARKED_CACHE[key] = (
            now,
            [{**trail, "coords": [list(p) for p in trail["coords"]]} for trail in trails],
        )
        while len(_WAYMARKED_CACHE) > 32:
            _WAYMARKED_CACHE.pop(next(iter(_WAYMARKED_CACHE)))
    return trails


def _discover(v3, center: dict[str, Any], radius_km: float) -> list[dict[str, Any]]:
    radius_m = max(3000, min(int(max(radius_km, 12.0) * 1000), 45000))
    query = (
        "[out:json][timeout:20];("
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"~\"^(hiking|foot|walking)$\"][\"network\"~\"^(iwn|nwn|rwn)$\"];"
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"~\"^(hiking|foot|walking)$\"][\"ref\"~\"^(GR|GRP)\",i];"
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


def _discover_generic(v3, center: dict[str, Any], radius_km: float) -> list[dict[str, Any]]:
    """Broader second-pass relation discovery used only after fast evidence misses."""
    radius_m = max(3000, min(int(max(radius_km, 12.0) * 1000), 45000))
    query = (
        "[out:json][timeout:20];("
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"~\"^(hiking|foot|walking)$\"][\"network\"~\"^(iwn|nwn|rwn|lwn)$\"];"
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"~\"^(hiking|foot|walking)$\"][\"ref\"];"
        f"relation(around:{radius_m},{center['lat']},{center['lon']})[\"route\"~\"^(hiking|foot|walking)$\"][\"name\"];"
        ");out geom tags 48;"
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
    trails.sort(key=lambda t: (
        0 if _fold(t.get("network")) in {"iwn", "nwn", "rwn"} else 1,
        0 if _fold(t.get("ref")).startswith("gr") else 1,
        -t["length_km"],
    ))
    return trails[:12]


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
    "_discover_waymarked", "_waymarked_trails_from_payloads", "_join_waymarked_lines",
]
