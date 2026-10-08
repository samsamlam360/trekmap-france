"""Bounded shop discovery beside already validated walking geometry.

Photon's reverse API can search OSM shop POIs by category, avoiding brittle
generic text searches for 'boulangerie' in a region-wide index. This module
only adds source-linked context, never alters routes or invents commerces.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from typing import Any

from . import free_planner_v2 as free


SHOPS = frozenset({
    "supermarket", "convenience", "bakery", "general",
    "grocery", "deli", "greengrocer", "food",
})
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"


def discover_near_route_shops(
    result: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if diagnostics is not None:
        diagnostics.update(status="not_attempted", attempts=0, responses=0)
    from . import trekbrain_resources_v9 as resources

    coords = ((result.get("route_preview") or {}).get("coords") or [])
    if not isinstance(coords, list) or len(coords) < 2:
        return []
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    day_points = resources._route_day_boundaries(result, days)
    if len(day_points) < 2:
        return []
    # Preserve the trailhead: on most routes it is a village and one of the
    # best places to buy provisions. For a closed loop, exclude only the
    # duplicate finish. For a traverse, retain both start and finish.
    # Search up to five geographically distributed daily anchors. They run
    # in a bounded parallel wave: adding trekking days should not leave all
    # intermediary villages unchecked.
    first = resources._point(day_points[0])
    last = resources._point(day_points[-1])
    closed = bool(first and last and resources._distance_km(first, last) <= 0.25)
    candidates = day_points[:-1] if closed else day_points
    count = min(5, len(candidates))
    indices = sorted({
        round(i * (len(candidates) - 1) / max(1, count - 1))
        for i in range(count)
    })
    # Real OSM villages near a walked stage are much better grocery probe
    # centres than arbitrary equal-distance mountain splits. Reposition only
    # intermediate probes; keep trailheads and traverse finish unchanged.
    # Require an actual OSM reference and a position <=2 km off the verified
    # footpath. No guessed place or extra HTTP request qualifies.
    profile = resources._route_distance_profile(coords)
    settlements = []
    for item in (result.get("points_of_interest") or []):
        if not isinstance(item, dict):
            continue
        tags = item.get("osm_tags") or {}
        tag_place = str(tags.get("place") or "").casefold() if isinstance(tags, dict) else ""
        label = str(item.get("category") or item.get("type") or "").casefold()
        if (
            tag_place not in {"village", "town", "hamlet", "city"}
            and not any(part in label for part in ("village", "bourg", "hameau", "town", "hamlet"))
        ):
            continue
        if not str(item.get("source_url") or "").startswith(
            "https://www.openstreetmap.org/"
        ):
            continue
        place = resources._point(item)
        matched = resources._route_match(coords, item, profile) if place else None
        if place and matched and matched[0] <= 2.0:
            settlements.append(place)

    anchors = []
    seen_anchors = set()
    village_probe_count = 0
    for index in indices:
        anchor = resources._point(candidates[index])
        if not anchor:
            continue
        if index != 0 and (closed or index != len(candidates) - 1):
            for _distance, town in sorted(
                (resources._distance_km(anchor, town), town)
                for town in settlements
            ):
                if _distance > 4.2:
                    break
                key = (round(town[0], 4), round(town[1], 4))
                if key not in seen_anchors:
                    anchor = town
                    village_probe_count += 1
                    break
        lat, lon = anchor
        if not (41.0 <= lat <= 51.6 and -5.6 <= lon <= 10.0):
            continue
        key = (round(lat, 4), round(lon, 4))
        if key not in seen_anchors:
            seen_anchors.add(key)
            anchors.append(anchor)
    if not anchors:
        return []

    if diagnostics is not None:
        diagnostics["village_probes"] = village_probe_count

    def probe(anchor: tuple[float, float]):
        lat, lon = anchor
        try:
            payload = free._request_json(
                PHOTON_REVERSE_URL,
                params={
                    "lat": round(lat, 6), "lon": round(lon, 6),
                    "radius": 5, "limit": 20, "osm_tag": "shop",
                    "lang": "fr",
                },
                timeout=1.8,
                ttl=7200,
                service="Photon reverse shops",
                retries=1,
                cache_empty=False,
            )
        except Exception:
            return [], False
        result_rows = []
        features = payload.get("features") if isinstance(payload, dict) else []
        for feature in features if isinstance(features, list) else []:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            code = str(props.get("countrycode") or "").upper()
            if code and code != "FR":
                continue
            shop = str(props.get("osm_value") or "").casefold()
            if str(props.get("osm_key") or "") != "shop" or shop not in SHOPS:
                continue
            kind = {"N": "node", "W": "way", "R": "relation"}.get(
                str(props.get("osm_type") or "").upper()
            )
            osm_id = props.get("osm_id")
            if not kind or osm_id is None:
                continue
            pt = (feature.get("geometry") or {}).get("coordinates") or []
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            try:
                flon, flat = float(pt[0]), float(pt[1])
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(flat) and math.isfinite(flon) and 41 <= flat <= 51.6 and -5.6 <= flon <= 10):
                continue
            item = {
                "name": str(props.get("name") or {
                    "bakery": "Boulangerie", "supermarket": "Supermarché",
                    "greengrocer": "Primeur",
                }.get(shop, "Épicerie"))[:160],
                "lat": flat, "lon": flon, "category": "food",
                "source_url": f"https://www.openstreetmap.org/{kind}/{osm_id}",
                "osm_tags": {"shop": shop},
                "display_only": True,
            }
            matched = resources._route_match(coords, item, profile)
            if matched and matched[0] <= resources.RESOURCE_LIMITS["food"]:
                result_rows.append((matched[0], item))
        return result_rows, True

    found = []
    responses = 0
    with ThreadPoolExecutor(max_workers=min(3, len(anchors))) as pool:
        futures = [pool.submit(probe, anchor) for anchor in anchors]
        for future in as_completed(futures):
            try:
                rows, responded = future.result()
                responses += int(responded)
                found.extend(rows or [])
            except Exception:
                pass
    if diagnostics is not None:
        diagnostics["attempts"] = len(anchors)
        diagnostics["responses"] = responses
    found.sort(key=lambda row: row[0])
    out, seen = [], set()
    for _distance, row in found:
        key = row["source_url"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= 12:
            break
    if diagnostics is not None:
        diagnostics["status"] = (
            "found" if out else "no_route_match" if responses else "unavailable"
        )
        diagnostics["accepted"] = len(out)
    return out


__all__ = ["discover_near_route_shops", "PHOTON_REVERSE_URL", "SHOPS"]
