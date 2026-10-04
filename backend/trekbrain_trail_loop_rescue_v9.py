"""Closed hiking-relation rescue for TrekBrain v9.

Some excellent multi-day loops already exist as complete OSM hiking relations.
Belle-Île-en-Mer's coastal GR is the motivating case: asking ORS to invent a
round trip is both less accurate and less reliable than using the actual hiking
relation that describes the loop.  This overlay therefore gives a closed,
continuous GR/GRP relation priority before the ORS round-trip fallback.

The geometry is never replaced by straight lines.  Tiny relation closure gaps may
be joined only by the normal pedestrian router, which itself has the independent
secondary-provider recovery installed in v9.
"""
from __future__ import annotations

from contextvars import ContextVar
import math
import re
import unicodedata
from typing import Any

from fastapi import HTTPException

_INSTALLED = False
_LAST_META: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_trail_loop_meta", default=None
)
_ACTIVE_INTENT: ContextVar[dict[str, Any] | None] = ContextVar(
    "trekbrain_v9_trail_loop_intent", default=None
)
_LAST_DISCOVERED_TRAILS: ContextVar[list[dict[str, Any]]] = ContextVar(
    "trekbrain_v9_trail_loop_discovered", default=[]
)
_DIRECT_CLOSE_KM = 0.10
_ROUTABLE_CLOSE_KM = 1.8
_MAX_START_OFFSET_KM = 12.0
_MAX_RELATION_GAP_KM = 2.2
_MAX_SECONDARY_POINTS = 21
_SECTION_MAX_ATTEMPTS = 2
# Sixteen Matrix locations (8 candidate endpoint/start pairs) are much more
# reliable on public ORS than the previous 24-location request, which produced
# intermittent HTTP 500s in production. We still keep enough distance/direction
# diversity to avoid overfitting the closure choice.
_SECTION_MATRIX_MAX_CANDIDATES = 8
_SECTION_DIVERSITY_KM = 2.0
_SECTION_JOIN_KM = 0.12
_SECTION_MAX_CLOSURE_SHARE = 0.42
_SECTION_MIN_RELATION_SHARE = 0.58


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _generic_relation_section_allowed(
    intent: dict[str, Any] | None,
    target_km: float,
    *,
    days_override: int | None = None,
    known_loop: bool = False,
) -> bool:
    """Allow section+pedestrian-closure for ordinary multi-day loops too.

    A route relation may be open in the local extract even when it is excellent
    hiking evidence. Rejecting it merely because the provider clipped the full
    circuit forces ORS to invent a huge loop. Safety remains unchanged: the
    section must be continuous, dominate the final geometry, fit the requested
    distance window, and its closure must be a real pedestrian route.
    """
    intent = intent or {}
    if not known_loop and _fold(intent.get("route_type") or "") != "boucle":
        return False
    try:
        days = int(days_override if days_override is not None else (intent.get("days") or 1))
        target = float(target_km or intent.get("total_target") or 0)
    except (TypeError, ValueError):
        return False
    if days < 2 or days > 12 or target < 24.0 or target > 260.0:
        return False
    # Open-relation closure is a heavier second-pass strategy. Short loops keep
    # the established fast router unless the coastal strategy explicitly opts in.
    if days < 5 and target < 90.0:
        return False
    if intent.get("start_query") or intent.get("end_query") or intent.get("via_query"):
        return False
    return True


def _coastal_section_allowed(intent: dict[str, Any] | None, target_km: float) -> bool:
    """Restrict the section-and-close strategy to genuine coastal loop intent.

    This deliberately does not change the generic inland dispatch. The previous
    experiment sent every coastal request through the full advanced planner and
    paid a large latency cost without improving geometry. Here we stay inside
    the fast round-trip path and use one already-discovered hiking relation only
    when the user's wording clearly asks for the coast/littoral.
    """
    intent = intent or {}
    if _fold(intent.get("route_type") or "") != "boucle":
        return False
    try:
        days = int(intent.get("days") or 1)
        target = float(target_km or intent.get("total_target") or 0)
    except (TypeError, ValueError):
        return False
    if days < 2 or days > 4 or target < 24.0 or target > 85.0:
        return False
    if intent.get("start_query") or intent.get("end_query") or intent.get("via_query"):
        return False
    if intent.get("max_dplus_day") or intent.get("avoid"):
        return False
    raw = _fold(intent.get("raw") or "")
    return bool(re.search(
        r"\b(?:sentiers?\s+cotiers?|chemins?\s+cotiers?|sentiers?\s+du\s+littoral|"
        r"littoral|bord\s+de\s+mer|cote\s+bretonne|cotes?\s+bretonnes?)\b",
        raw,
    ))



def _relation_first_allowed(
    intent: dict[str, Any] | None,
    target_km: float,
    days: int,
) -> bool:
    """Gate the expensive relation-discovery stack to requests that benefit.

    Closed/open hiking-relation discovery is valuable for named tours, coastal
    itineraries and long multi-day loops. Running Overpass + Waymarked +
    hydration before every ordinary two/three-day loop adds large cold latency
    and often falls back to the same ORS round trip anyway.
    """
    intent = intent or {}
    if _coastal_section_allowed(intent, target_km):
        return True
    if _generic_relation_section_allowed(
        intent,
        target_km,
        days_override=days,
        known_loop=True,
    ):
        return True

    raw = _fold(intent.get("raw") or "")
    if not raw:
        return False

    # Explicit long-distance trail/network wording.
    if re.search(r"\b(?:gr|grp)\s*\d*\b", raw):
        return True
    if re.search(r"\bgrande\s+randonnee\b", raw):
        return True

    # Named-tour wording such as "Tour des Fiz" should stay evidence-first even
    # below the generic long-loop threshold. Ordinary "autour du Hohneck" or
    # "privilégier les sentiers" deliberately does not match this.
    if re.search(
        r"\b(?:tour|circuit)\s+(?:du|de\s+la|des|de\s+l[' ]|d[' ])\s*[a-z0-9]",
        raw,
    ):
        return True

    # Strong request to reuse an existing named/official itinerary.
    if any(phrase in raw for phrase in (
        "itineraire de randonnee existant",
        "itineraire existant",
        "vrai trace",
        "trace officiel",
        "trace officielle",
        "boucle artificielle",
    )):
        return True
    return False


def _trail_rejection_snapshot(
    trails: list[dict[str, Any]],
    start: dict[str, Any],
    limit: int = 6,
) -> str:
    """Compact local diagnostics for relation candidates rejected pre-Matrix."""
    rows = []
    for trail in list(trails or [])[: max(1, int(limit))]:
        coords = trail.get("coords") or []
        try:
            length_km = float(trail.get("length_km") or _length(coords))
        except (TypeError, ValueError):
            length_km = 0.0
        try:
            _idx, start_off = _nearest_index(coords, start)
        except Exception:
            start_off = float("inf")
        try:
            gap = _max_gap(coords)
        except Exception:
            gap = float("inf")
        label = str(trail.get("ref") or trail.get("name") or trail.get("id") or "trail")
        rows.append(
            f"{label[:24]}:{len(coords)}pt/{length_km:.1f}km/"
            f"off={start_off:.1f}/gap={gap:.1f}"
        )
    return "|".join(rows)[:700]


def _dist(a, b) -> float:
    if isinstance(a, dict):
        a = [a["lat"], a["lon"]]
    if isinstance(b, dict):
        b = [b["lat"], b["lon"]]
    lat1, lon1, lat2, lon2 = map(math.radians, (float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _length(coords) -> float:
    return sum(_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:]))


def _max_gap(coords) -> float:
    return max((_dist(a, b) for a, b in zip(coords or [], (coords or [])[1:])), default=0.0)


def _nearest_index(coords, point) -> tuple[int, float]:
    if not coords:
        return 0, float("inf")
    best_i, best_d = 0, float("inf")
    for i, coord in enumerate(coords):
        value = _dist(coord, point)
        if value < best_d:
            best_i, best_d = i, value
    return best_i, best_d


def _intent_tokens() -> set[str]:
    raw = _fold((_ACTIVE_INTENT.get() or {}).get("raw") or "")
    stop = {
        "je", "veux", "faire", "un", "une", "de", "du", "des", "le", "la", "les",
        "en", "dans", "sur", "pour", "avec", "trek", "randonnee", "jours", "jour",
        "km", "environ", "autour", "boucle", "tour",
    }
    return {
        token for token in re.findall(r"[a-z0-9]{3,}", raw)
        if token not in stop and not token.isdigit()
    }


def _trail_text_score(trail: dict[str, Any]) -> float:
    """Reward evidence whose name/ref actually matches the user's wording."""
    tokens = _intent_tokens()
    if not tokens:
        return 0.0
    text = _fold(f"{trail.get('ref') or ''} {trail.get('name') or ''}")
    matched = sum(1 for token in tokens if token in text)
    # A named match is stronger evidence than the old GR-specific tie-break.
    return -min(30.0, matched * 8.0)


def _preferred_score(trail: dict[str, Any], target_km: float, start_off: float, length_km: float) -> float:
    network = _fold(trail.get("network") or "")
    network_bonus = -5.0 if network in {"iwn", "nwn", "rwn"} else 0.0
    return (
        abs(length_km - float(target_km))
        + start_off * 0.7
        + network_bonus
        + _trail_text_score(trail)
    )


def _close_relation(coords, legacy_distance=None):
    """Return a real closed geometry or None.

    A sub-100 m endpoint discrepancy is normal relation bookkeeping and may be
    closed directly.  Larger gaps must be joined by an actual pedestrian router.
    """
    if len(coords) < 4:
        return None, "relation trop courte"
    coords = [[float(p[0]), float(p[1])] for p in coords]
    if _max_gap(coords) > _MAX_RELATION_GAP_KM:
        return None, "relation discontinue"
    closure = _dist(coords[-1], coords[0])
    if closure <= _DIRECT_CLOSE_KM:
        if coords[-1] != coords[0]:
            coords.append(list(coords[0]))
        return coords, None
    if closure > _ROUTABLE_CLOSE_KM:
        return None, f"relation non fermée ({closure:.1f} km)"

    try:
        from . import ors
        routed = ors.get_route([coords[-1], coords[0]], legacy_distance or _length)
    except Exception as exc:
        return None, f"fermeture pédestre indisponible ({exc.__class__.__name__})"
    if not isinstance(routed, dict) or routed.get("fallback") is not False:
        return None, "fermeture pédestre non validée"
    connector = routed.get("coords") or []
    if len(connector) < 2:
        return None, "fermeture pédestre vide"
    for point in connector[1:]:
        if point != coords[-1]:
            coords.append([float(point[0]), float(point[1])])
    if _dist(coords[-1], coords[0]) > 0.05:
        return None, "fermeture pédestre incomplète"
    if coords[-1] != coords[0]:
        coords.append(list(coords[0]))
    return coords, None


def _rotate_closed(coords, index: int):
    if len(coords) < 4:
        return coords
    ring = list(coords)
    if _dist(ring[0], ring[-1]) <= 0.05:
        ring = ring[:-1]
    if not ring:
        return coords
    index = max(0, min(int(index), len(ring) - 1))
    out = ring[index:] + ring[:index]
    out.append(list(out[0]))
    return out


def _relation_loop(v3, gr, start: dict[str, Any], target_km: float):
    radius = min(45.0, max(14.0, float(target_km) * 0.36))
    try:
        trails = list(gr._discover(v3, start, radius) or [])
    except Exception as exc:
        return None, f"découverte des GR impossible ({exc.__class__.__name__})"
    _LAST_DISCOVERED_TRAILS.set(trails)

    rows = []
    reasons = []
    for trail in trails:
        raw = trail.get("coords") or []
        if len(raw) < 8:
            continue
        closed, reason = _close_relation(raw, _length)
        if not closed:
            if reason:
                reasons.append(reason)
            continue
        relation_km = _length(closed)
        # Avoid selecting a tiny local circuit or a huge national relation merely
        # because it passes near the requested place.
        if relation_km < max(10.0, float(target_km) * 0.62) or relation_km > float(target_km) * 1.42:
            continue
        idx, start_off = _nearest_index(closed[:-1], start)
        if start_off > _MAX_START_OFFSET_KM:
            continue
        score = _preferred_score(trail, target_km, start_off, relation_km)
        rows.append((score, trail, closed, idx, start_off, relation_km))

    if not rows:
        # Overpass can return perfectly valid but irrelevant local relations. The
        # old planner stopped there and never consulted its secondary index.
        # Merge Waymarked candidates before giving up so an unseen named route
        # can still win by distance/name/continuity evidence.
        # Tier 2: broaden Overpass only after the fast GR/high-network query
        # produced no compatible closed candidate.
        try:
            generic = list(gr._discover_generic(v3, start, radius) or [])
        except Exception:
            generic = []
        known = {
            str(x.get("id") or x.get("source_url") or x.get("ref") or x.get("name") or "")
            for x in trails
        }
        merged = list(trails)
        for trail in generic:
            identity = str(trail.get("id") or trail.get("source_url") or trail.get("ref") or trail.get("name") or "")
            if identity and identity not in known:
                known.add(identity)
                merged.append(trail)

        # Tier 3: use the independent Waymarked OSM route index if Overpass still
        # has not supplied enough evidence.
        try:
            secondary = list(gr._discover_waymarked(start, radius) or [])
        except Exception:
            secondary = []
        known = {
            str(x.get("id") or x.get("source_url") or x.get("ref") or x.get("name") or "")
            for x in merged
        }
        # Preserve generic candidates already merged above.
        for trail in secondary:
            identity = str(trail.get("id") or trail.get("source_url") or trail.get("ref") or trail.get("name") or "")
            if identity and identity not in known:
                known.add(identity)
                merged.append(trail)
        if len(merged) > len(trails):
            _LAST_DISCOVERED_TRAILS.set(merged)
            for trail in merged:
                if trail in trails:
                    continue
                raw = trail.get("coords") or []
                if len(raw) < 8:
                    continue
                closed, reason = _close_relation(raw, _length)
                if not closed:
                    if reason:
                        reasons.append(reason)
                    continue
                relation_km = _length(closed)
                if relation_km < max(10.0, float(target_km) * 0.62) or relation_km > float(target_km) * 1.42:
                    continue
                idx, start_off = _nearest_index(closed[:-1], start)
                if start_off > _MAX_START_OFFSET_KM:
                    continue
                score = _preferred_score(trail, target_km, start_off, relation_km)
                rows.append((score, trail, closed, idx, start_off, relation_km))

    if not rows and secondary:
        # /list/segments is clipped to the discovery bbox. For long established
        # tours that clipped geometry can look open even though the underlying
        # OSM relation is a real loop. Hydrate only the two strongest Waymarked
        # candidates from the provider's full relation tree before inventing a
        # generic loop or accepting a large interior closure.
        hydrate = getattr(gr, "_hydrate_waymarked_relation", None)
        ranked_secondary = []
        if callable(hydrate):
            for candidate in secondary:
                raw = candidate.get("coords") or []
                if len(raw) < 8:
                    continue
                idx, start_off = _nearest_index(raw, start)
                if start_off > max(_MAX_START_OFFSET_KM, 18.0):
                    continue
                length_km = float(candidate.get("length_km") or _length(raw))
                ranked_secondary.append((
                    _preferred_score(candidate, target_km, start_off, length_km),
                    candidate,
                ))
            ranked_secondary.sort(key=lambda row: row[0])

        hydrated = []
        for _score, candidate in ranked_secondary[:2]:
            try:
                full = hydrate(candidate)
            except Exception:
                full = None
            if not isinstance(full, dict):
                continue
            hydrated.append(full)
            raw = full.get("coords") or []
            if len(raw) < 8:
                continue
            closed, reason = _close_relation(raw, _length)
            if not closed:
                if reason:
                    reasons.append(reason)
                continue
            relation_km = _length(closed)
            if (
                relation_km < max(10.0, float(target_km) * 0.62)
                or relation_km > float(target_km) * 1.42
            ):
                continue
            idx, start_off = _nearest_index(closed[:-1], start)
            if start_off > _MAX_START_OFFSET_KM:
                continue
            score = _preferred_score(full, target_km, start_off, relation_km)
            rows.append((score, full, closed, idx, start_off, relation_km))

        if hydrated:
            # Keep the authoritative full geometry available to the section
            # fallback too, in case the relation is genuinely open rather than
            # merely bbox-clipped.
            full_by_id = {
                str(row.get("id")): row
                for row in hydrated
                if row.get("id") is not None
            }
            refreshed = []
            for row in (_LAST_DISCOVERED_TRAILS.get() or merged):
                replacement = full_by_id.get(str(row.get("id")))
                refreshed.append(replacement or row)
            known_ids = {str(row.get("id")) for row in refreshed if row.get("id") is not None}
            for row in hydrated:
                if row.get("id") is None or str(row.get("id")) not in known_ids:
                    refreshed.append(row)
            _LAST_DISCOVERED_TRAILS.set(refreshed)
            _coastal_section_log(
                "full-relation-recovery",
                attempted=min(2, len(ranked_secondary)),
                hydrated=len(hydrated),
                accepted=len(rows),
                target=round(float(target_km), 1),
            )

    if not rows:
        detail = reasons[0] if reasons else "aucune relation fermée de longueur compatible"
        return None, detail
    rows.sort(key=lambda row: row[0])
    _, trail, closed, idx, start_off, relation_km = rows[0]
    rotated = _rotate_closed(closed, idx)
    if len(rotated) < 4 or _max_gap(rotated) > _MAX_RELATION_GAP_KM:
        return None, "géométrie GR finale discontinue"

    first = rotated[0]
    # The generic round-trip fallback otherwise starts at a geocoded centre,
    # which can sit several kilometres inland.  With no explicit fixed departure
    # in that fallback, start on the actual hiking relation instead.
    start["lat"] = float(first[0])
    start["lon"] = float(first[1])
    ref = str(trail.get("ref") or "").strip()
    label = ref or str(trail.get("name") or "itinéraire balisé").strip()
    start["name"] = f"Départ sur {label}"[:120]
    start["category"] = "trail"

    result = {
        "coords": rotated,
        "distance": round(_length(rotated), 2),
        "fallback": False,
        "routing_mode": "osm-hiking-relation-loop",
        "profile": "hiking-relation",
        "provider": "OpenStreetMap hiking relation",
        "relation_ref": ref,
        "relation_name": str(trail.get("name") or "")[:160],
        "relation_source_url": trail.get("source_url"),
        "relation_geometry": True,
        "start_offset_before_snap_km": round(float(start_off), 2),
    }
    _LAST_META.set({
        "ref": ref,
        "name": str(trail.get("name") or "")[:160],
        "source_url": trail.get("source_url"),
        "distance_km": round(relation_km, 2),
    })
    return result, None


def _section_path(coords, start_idx: int, end_idx: int) -> list[list[float]]:
    if end_idx >= start_idx:
        return [list(p) for p in coords[start_idx:end_idx + 1]]
    return [list(p) for p in reversed(coords[end_idx:start_idx + 1])]


def _section_start_offset_limit(target_km: float) -> float:
    """Allow a modest regional-centre snap for long loops only.

    Generic relation-section rescue is disabled whenever the user supplied an
    explicit start/end/via constraint. For a long regional loop, however, the
    geocoded place is only an area anchor; insisting on exactly 12 km can reject
    a strong long-distance trail for a few hundred metres. Keep short loops at
    the historical 12 km limit and grow gently, capped at 18 km.
    """
    try:
        target = max(0.0, float(target_km))
    except (TypeError, ValueError):
        target = 0.0
    return max(_MAX_START_OFFSET_KM, min(18.0, target * 0.12))


def _section_candidates(trails, start: dict[str, Any], target_km: float):
    """Rank long real hiking-relation sections before making any routing call."""
    rows = []
    target = float(target_km)
    for trail in trails or []:
        coords = [[float(p[0]), float(p[1])] for p in (trail.get("coords") or [])]
        if len(coords) < 18:
            continue
        relation_km = float(trail.get("length_km") or _length(coords))
        if relation_km < target * 0.62:
            continue
        start_idx, start_off = _nearest_index(coords, start)
        if start_off > _section_start_offset_limit(target):
            continue

        for direction in (1, -1):
            arc = 0.0
            prev = start_idx
            idx = start_idx + direction
            while 0 <= idx < len(coords):
                step = _dist(coords[prev], coords[idx])
                if step > _MAX_RELATION_GAP_KM:
                    break
                arc += step
                if arc > target * 0.94:
                    break
                if arc >= target * 0.54:
                    closure_air = _dist(coords[idx], coords[start_idx])
                    if 0.35 <= closure_air <= target * 0.43:
                        estimated = arc + closure_air * 1.28
                        # Prefer a distance fit, then more time on the marked
                        # corridor and a departure close to the requested area.
                        score = (
                            abs(estimated - target)
                            + max(0.0, 0.68 - arc / max(target, 0.1)) * 12.0
                            + start_off * 0.35
                            + _trail_text_score(trail)
                        )
                        rows.append((
                            score,
                            trail,
                            _section_path(coords, start_idx, idx),
                            start_off,
                            arc,
                            direction,
                        ))
                prev = idx
                idx += direction
    rows.sort(key=lambda row: row[0])
    return rows


def _diverse_section_candidates(rows, limit: int = _SECTION_MATRIX_MAX_CANDIDATES):
    """Keep useful distance/direction diversity before one bounded Matrix call."""
    chosen = []
    buckets = set()
    for row in rows or []:
        _score, trail, _section, _start_off, section_km, direction = row
        identity = str(trail.get("id") or trail.get("ref") or trail.get("name") or "")
        bucket = int(round(float(section_km) / _SECTION_DIVERSITY_KM))
        key = (identity, int(direction), bucket)
        if key in buckets:
            continue
        buckets.add(key)
        chosen.append(row)
        if len(chosen) >= max(1, int(limit)):
            break
    return chosen


def _matrix_rank_section_candidates(rows, ors, target_km: float, feasible_low: float, feasible_high: float):
    """Use one real pedestrian Matrix to rank closure endpoints.

    Each candidate contributes exactly two Matrix locations: its relation endpoint
    and its own snapped relation start. Twelve candidates therefore fit the local
    24-location ORS Matrix cap. The Matrix chooses plausibly sized closures; only
    the best one or two then need Directions geometry.
    """
    shortlist = _diverse_section_candidates(rows)
    if not shortlist:
        return [], False, "aucune section diverse à évaluer"

    matrix_coords = []
    for _score, _trail, section, _start_off, _section_km, _direction in shortlist:
        if len(section) < 2:
            continue
        matrix_coords.extend([section[-1], section[0]])
    if len(matrix_coords) != len(shortlist) * 2:
        return [], False, "sections incomplètes avant Matrix"

    try:
        result = ors.get_distance_matrix(matrix_coords)
    except Exception as exc:
        return [], False, f"Matrix fermeture indisponible ({exc.__class__.__name__})"
    matrix = result.get("distances") if isinstance(result, dict) else None
    if not matrix or len(matrix) < len(matrix_coords):
        warning = str((result or {}).get("warning") or "Matrix fermeture incomplète")
        return [], False, warning

    ranked = []
    target = float(target_km)
    for index, row in enumerate(shortlist):
        _rough_score, trail, section, start_off, section_km, direction = row
        endpoint_idx = index * 2
        start_idx = endpoint_idx + 1
        try:
            closure_km = matrix[endpoint_idx][start_idx]
        except (IndexError, TypeError):
            closure_km = None
        if closure_km is None:
            continue
        try:
            closure_km = float(closure_km)
        except (TypeError, ValueError):
            continue
        if closure_km <= 0.2:
            continue
        estimated_total = float(section_km) + closure_km
        if estimated_total < feasible_low or estimated_total > feasible_high:
            continue
        closure_share = closure_km / max(estimated_total, 0.1)
        relation_share = float(section_km) / max(estimated_total, 0.1)
        if closure_share > _SECTION_MAX_CLOSURE_SHARE or relation_share < _SECTION_MIN_RELATION_SHARE:
            continue
        score = (
            abs(estimated_total - target)
            + closure_share * 6.0
            + float(start_off) * 0.30
            + _trail_text_score(trail)
        )
        ranked.append((
            score, trail, section, start_off, section_km, direction,
            closure_km, estimated_total,
        ))
    ranked.sort(key=lambda row: row[0])
    return ranked, True, None


def _coastal_section_log(event: str, **values) -> None:
    bits = [f"{key}={value}" for key, value in values.items()]
    print(f"[TrekBrain v9][coastal-section] {event} " + " ".join(bits), flush=True)


def _relation_section_loop(
    v3,
    gr,
    start: dict[str, Any],
    target_km: float,
    daily_min: float,
    daily_max: float,
    days: int,
    trails=None,
):
    """Extract a real long-distance trail section and close it on foot.

    The coastal section remains untouched. Only the final return to the same
    trail departure is delegated to the pedestrian router. No straight-line
    bridge is accepted, and at most two closure candidates are routed.
    """
    trails = list(trails if trails is not None else (_LAST_DISCOVERED_TRAILS.get() or []))
    # Primary discovery may return several perfectly valid but irrelevant local
    # relations. Treating a non-empty list as "discovery succeeded" prevented the
    # secondary route index from ever contributing the long/named itinerary the
    # request actually needed. Merge both evidence sources, then rank them.
    radius = min(45.0, max(16.0, float(target_km) * 0.42))
    try:
        secondary = list(gr._discover_waymarked(start, radius) or [])
    except Exception:
        secondary = []
    if secondary:
        known = {
            str(x.get("id") or x.get("source_url") or x.get("ref") or x.get("name") or "")
            for x in trails
        }
        added = 0
        for trail in secondary:
            identity = str(trail.get("id") or trail.get("source_url") or trail.get("ref") or trail.get("name") or "")
            if identity and identity in known:
                continue
            if identity:
                known.add(identity)
            trails.append(trail)
            added += 1
        _coastal_section_log(
            "secondary-trails",
            provider="waymarked",
            trails=len(secondary),
            added=added,
            combined=len(trails),
            longest=round(max(float(x.get("length_km") or 0) for x in secondary), 1),
        )
    _LAST_DISCOVERED_TRAILS.set(trails)
    if not trails:
        _coastal_section_log("no-trails", target=round(float(target_km), 1))
        return None, "aucune relation longue de randonnée trouvée"

    rows = _section_candidates(trails, start, target_km)
    if not rows:
        _coastal_section_log(
            "no-candidates",
            trails=len(trails),
            target=round(float(target_km), 1),
            snapshot=_trail_rejection_snapshot(trails, start),
        )
        return None, "aucune section de relation côtière compatible"

    feasible_low = max(float(target_km) * 0.82, float(daily_min) * max(days, 1) * 0.90)
    feasible_high = min(float(target_km) * 1.18, float(daily_max) * max(days, 1) + 0.75)
    evaluated = []
    warnings = []
    route_rejections = []

    def reject(reason: str) -> None:
        reason = str(reason or "fermeture rejetée")
        warnings.append(reason)
        route_rejections.append(reason)

    from . import ors

    matrix_ranked, matrix_ok, matrix_warning = _matrix_rank_section_candidates(
        rows, ors, target_km, feasible_low, feasible_high
    )
    if matrix_ok:
        route_rows = matrix_ranked[:_SECTION_MAX_ATTEMPTS]
        _coastal_section_log(
            "matrix-select",
            candidates=len(rows),
            shortlist=len(_diverse_section_candidates(rows)),
            viable=len(matrix_ranked),
            target=round(float(target_km), 1),
        )
        if not route_rows:
            # Matrix is a ranking optimisation, not the final geometry validator.
            # A public Matrix can snap endpoint pairs differently from Directions,
            # especially on sparse mountain networks. Give at most two diverse,
            # already-ranked relation sections one exact Directions attempt; the
            # strict distance/share/gap/retrace checks below remain authoritative.
            route_rows = [
                (score, trail, section, start_off, section_km, direction, None, None)
                for score, trail, section, start_off, section_km, direction
                in _diverse_section_candidates(rows)[:_SECTION_MAX_ATTEMPTS]
            ]
            _coastal_section_log(
                "matrix-zero-viable-fallback",
                candidates=len(rows),
                routed=len(route_rows),
                target=round(float(target_km), 1),
            )
    else:
        # Matrix is an optimisation/selection layer, not a safety dependency.
        # Preserve the old bounded two-candidate fallback if the provider is down.
        route_rows = [
            (score, trail, section, start_off, section_km, direction, None, None)
            for score, trail, section, start_off, section_km, direction
            in _diverse_section_candidates(rows)[:_SECTION_MAX_ATTEMPTS]
        ]
        if matrix_warning:
            warnings.append(matrix_warning)
        _coastal_section_log(
            "matrix-fallback",
            candidates=len(rows),
            reason=(matrix_warning or "unknown")[:80],
        )

    for _rank, trail, section, start_off, section_km, direction, matrix_closure_km, matrix_total_km in route_rows:
        if len(section) < 8 or _max_gap(section) > _MAX_RELATION_GAP_KM:
            continue
        start_coord = section[0]
        end_coord = section[-1]
        try:
            connector = ors.get_route([end_coord, start_coord], _length)
        except Exception as exc:
            reject(f"fermeture intérieure indisponible ({exc.__class__.__name__})")
            continue
        if not isinstance(connector, dict) or connector.get("fallback") is not False:
            reject(str((connector or {}).get("warning") or "fermeture intérieure non validée"))
            continue
        connector_coords = [
            [float(p[0]), float(p[1])]
            for p in (connector.get("coords") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 2
        ]
        if len(connector_coords) < 2:
            reject("fermeture intérieure vide")
            continue
        if _dist(end_coord, connector_coords[0]) > _SECTION_JOIN_KM:
            reject("départ de fermeture trop éloigné du sentier")
            continue
        if _dist(connector_coords[-1], start_coord) > _SECTION_JOIN_KM:
            reject("retour intérieur trop éloigné du départ")
            continue

        merged = [list(p) for p in section]
        for point in connector_coords[1:]:
            if point != merged[-1]:
                merged.append(point)
        if _dist(merged[-1], start_coord) <= _DIRECT_CLOSE_KM and merged[-1] != start_coord:
            merged.append(list(start_coord))
        if _dist(merged[-1], start_coord) > _SECTION_JOIN_KM:
            reject("boucle côtière non refermée")
            continue

        total = _length(merged)
        closure_km = _length(connector_coords)
        closure_share = closure_km / max(total, 0.1)
        relation_share = float(section_km) / max(total, 0.1)
        if total < feasible_low or total > feasible_high:
            reject(f"section refermée hors cible ({total:.1f} km)")
            continue
        if closure_share > _SECTION_MAX_CLOSURE_SHARE or relation_share < _SECTION_MIN_RELATION_SHARE:
            reject("fermeture intérieure trop importante par rapport au sentier")
            continue
        gap = _max_gap(merged)
        if gap > _MAX_RELATION_GAP_KM:
            reject(f"géométrie section+fermeture discontinue ({gap:.1f} km)")
            continue
        retrace = (
            float(v3._route_retrace_ratio(merged))
            if hasattr(v3, "_route_retrace_ratio")
            else 0.0
        )
        if retrace > 0.44:
            reject(f"boucle trop répétitive ({retrace:.2f})")
            continue

        score = (
            abs(total - float(target_km))
            + closure_share * 6.0
            + retrace * 14.0
            + float(start_off) * 0.30
        )
        evaluated.append((
            score, trail, merged, start_off, section_km, closure_km,
            relation_share, closure_share, direction, retrace,
        ))

    if not evaluated:
        failure = (
            route_rejections[0]
            if route_rejections
            else warnings[0] if warnings
            else "aucune fermeture intérieure validée"
        )
        _coastal_section_log(
            "rejected",
            routed=len(route_rows),
            first_reason=str(failure)[:100],
        )
        return None, str(failure)

    evaluated.sort(key=lambda row: row[0])
    (
        _score, trail, merged, start_off, section_km, closure_km,
        relation_share, closure_share, direction, retrace,
    ) = evaluated[0]

    first = merged[0]
    start["lat"] = float(first[0])
    start["lon"] = float(first[1])
    ref = str(trail.get("ref") or "").strip()
    label = ref or str(trail.get("name") or "itinéraire balisé").strip()
    start["name"] = f"Départ sur {label}"[:120]
    start["category"] = "trail"

    result = {
        "coords": merged,
        "distance": round(_length(merged), 2),
        "fallback": False,
        "routing_mode": "osm-hiking-relation-section-loop",
        "profile": "hiking-relation+pedestrian-closure",
        "provider": "OpenStreetMap hiking relation + pedestrian closure",
        "relation_ref": ref,
        "relation_name": str(trail.get("name") or "")[:160],
        "relation_source_url": trail.get("source_url"),
        "relation_geometry": True,
        "relation_section_km": round(float(section_km), 2),
        "closure_route_km": round(float(closure_km), 2),
        "relation_share": round(float(relation_share), 3),
        "closure_share": round(float(closure_share), 3),
        "section_direction": int(direction),
        "section_retrace_ratio": round(float(retrace), 4),
        "start_offset_before_snap_km": round(float(start_off), 2),
    }
    _coastal_section_log(
        "accepted",
        ref=(ref or "trail"),
        total=round(_length(merged), 1),
        section=round(float(section_km), 1),
        closure=round(float(closure_km), 1),
        relation_share=round(float(relation_share), 2),
    )
    _LAST_META.set({
        "ref": ref,
        "name": str(trail.get("name") or "")[:160],
        "source_url": trail.get("source_url"),
        "distance_km": result["distance"],
        "section_km": result["relation_section_km"],
        "closure_km": result["closure_route_km"],
        "relation_share": result["relation_share"],
        "mode": result["routing_mode"],
    })
    return result, None


def _compact_route_points(points):
    """Keep every overnight detour while staying under secondary-router budget."""
    if len(points) <= _MAX_SECONDARY_POINTS:
        return points
    fixed = {0, len(points) - 1}
    for i, point in enumerate(points):
        category = str((point or {}).get("category") or "").casefold()
        if category in {"camping", "refuge"}:
            fixed.add(i)
            if i > 0:
                fixed.add(i - 1)
            if i + 1 < len(points):
                fixed.add(i + 1)
    remaining = [i for i in range(1, len(points) - 1) if i not in fixed]
    budget = max(0, _MAX_SECONDARY_POINTS - len(fixed))
    if budget and remaining:
        if budget >= len(remaining):
            fixed.update(remaining)
        else:
            for n in range(budget):
                pos = round((len(remaining) - 1) * n / max(1, budget - 1)) if budget > 1 else len(remaining) // 2
                fixed.add(remaining[pos])
    return [points[i] for i in sorted(fixed)]


def install_trail_loop_rescue(roundtrip, gr) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_best = roundtrip._best_roundtrip
    original_points = roundtrip._route_points_with_stays
    original_build_roundtrip = roundtrip._build_roundtrip

    def best_roundtrip(start, target_km, daily_min, daily_max, days, v3):
        _LAST_META.set(None)
        _LAST_DISCOVERED_TRAILS.set([])
        intent = _ACTIVE_INTENT.get()

        # Do not make every small generic loop pay the full Overpass/Waymarked
        # relation-discovery stack before the already-bounded ORS round trip.
        if not _relation_first_allowed(intent, target_km, days):
            return original_best(start, target_km, daily_min, daily_max, days, v3)

        relation, relation_warning = _relation_loop(v3, gr, start, target_km)
        if relation is not None:
            return relation

        section_warning = None
        generic_allowed = _generic_relation_section_allowed(
            intent,
            target_km,
            days_override=days,
            known_loop=True,
        )
        if _coastal_section_allowed(intent, target_km) or generic_allowed:
            section, section_warning = _relation_section_loop(
                v3,
                gr,
                start,
                target_km,
                daily_min,
                daily_max,
                days,
                trails=_LAST_DISCOVERED_TRAILS.get(),
            )
            if section is not None:
                return section

        try:
            return original_best(start, target_km, daily_min, daily_max, days, v3)
        except HTTPException as exc:
            detail = str(getattr(exc, "detail", exc) or "")
            warnings = [x for x in (relation_warning, section_warning) if x]
            if warnings:
                detail = f"{detail} Secours GR/GRP: {' ; '.join(warnings)}.".strip()
            raise HTTPException(status_code=exc.status_code, detail=detail)

    def compact_points(coords, start, stays, days):
        return _compact_route_points(original_points(coords, start, stays, days))

    def build_roundtrip(data, legacy_main, v3):
        token = None
        try:
            try:
                token = _ACTIVE_INTENT.set(v3._parse_intent(data))
            except Exception:
                token = _ACTIVE_INTENT.set(None)

            result = original_build_roundtrip(data, legacy_main, v3)
            route_preview = result.get("route_preview") or {}
            route_mode = str(route_preview.get("routing_mode") or "")
            if route_mode in {"osm-hiking-relation-loop", "osm-hiking-relation-section-loop"}:
                meta = _LAST_META.get() or {}
                ref = str(meta.get("ref") or "GR/GRP").strip()
                section_mode = route_mode == "osm-hiking-relation-section-loop"
                if section_mode:
                    result["description"] = (
                        f"Boucle construite sur une section réelle de {ref}, puis refermée par un itinéraire pédestre intérieur."
                    )
                    notes = [
                        f"Le tracé suit d'abord une section réellement cartographiée de {ref}, puis revient au départ par une liaison pédestre routée.",
                        (
                            f"Environ {float(meta.get('section_km') or 0):.1f} km suivent la relation de randonnée "
                            f"et {float(meta.get('closure_km') or 0):.1f} km servent à refermer la boucle."
                        ),
                        "Aucune ligne droite n'est utilisée pour fermer le circuit ; la liaison intérieure doit être validée par le routeur pédestre.",
                    ]
                else:
                    result["description"] = (
                        f"Boucle basée sur la relation de randonnée {ref} réellement cartographiée dans OpenStreetMap."
                    )
                    notes = [
                        f"Le tracé principal suit la relation de randonnée {ref} au lieu de demander à ORS d'inventer une boucle.",
                        "La relation de randonnée est une forte preuve de cheminement, mais l'état du sentier et les éventuelles déviations restent à vérifier avant le départ.",
                    ]
                if result.get("accommodations"):
                    notes.append("Les détours vers les nuitées ont été recalculés séparément sur le réseau pédestre.")
                result["advisor_notes"] = notes
                result["planner_fallback"] = route_mode
                confidence = result.setdefault("confidence", {})
                confidence["score"] = max(int(confidence.get("score") or 0), 84 if not section_mode else 82)
                confidence["limitations"] = [
                    "Relation OSM de randonnée utilisée comme axe principal ; vérifier fermetures et déviations temporaires."
                ]
                route_preview["provider"] = (
                    "OpenStreetMap hiking relation + pedestrian closure"
                    if section_mode else "OpenStreetMap hiking relation"
                )
                route_preview["relation_ref"] = meta.get("ref")
                route_preview["relation_name"] = meta.get("name")
                route_preview["relation_source_url"] = meta.get("source_url")
                if section_mode:
                    route_preview["relation_section_km"] = meta.get("section_km")
                    route_preview["closure_route_km"] = meta.get("closure_km")
                    route_preview["relation_share"] = meta.get("relation_share")
            return result
        finally:
            if token is not None:
                _ACTIVE_INTENT.reset(token)

    roundtrip._best_roundtrip = best_roundtrip
    roundtrip._route_points_with_stays = compact_points
    roundtrip._build_roundtrip = build_roundtrip


__all__ = [
    "install_trail_loop_rescue",
    "_relation_loop",
    "_relation_section_loop",
    "_section_candidates",
    "_section_start_offset_limit",
    "_diverse_section_candidates",
    "_matrix_rank_section_candidates",
    "_coastal_section_allowed",
    "_relation_first_allowed",
    "_trail_rejection_snapshot",
    "_compact_route_points",
]
