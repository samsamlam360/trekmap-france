"""Persistent, positive-only OSM POI cache for TrekBrain's validated hiking line.

Stores source-linked evidence in TrekMap's existing PostGIS database. The cache
does NOT assert that shops are currently open or water is potable, does NOT
cache missing results, and never changes a route's walking geometry.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any

from sqlalchemy import text

OSM_SOURCE = re.compile(r"^https://www\.openstreetmap\.org/(?:node|way|relation)/[1-9][0-9]*$")
KINDS = frozenset({"food", "water", "camping", "refuge", "lodging"})
MAX_STORED_PER_PLAN = 110
MAX_LOADED_PER_PLAN = 700
FRESH_DAYS = 10


def _candidate(point: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(point, dict):
        return None
    source = str(point.get("source_url") or "").strip()
    category = str(point.get("category") or point.get("kind") or "").lower()
    if category not in KINDS or not OSM_SOURCE.fullmatch(source):
        return None
    tags = point.get("osm_tags")
    if isinstance(tags, dict) and (
        tags.get("access") == "private"
        or tags.get("disused") == "yes"
        or tags.get("shop") == "vacant"
        or tags.get("abandoned") == "yes"
    ):
        return None
    try:
        lat, lon = float(point["lat"]), float(point["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and 41 <= lat <= 52 and -6 <= lon <= 11):
        return None
    try:
        encoded_tags = json.dumps(
            tags if isinstance(tags, dict) else {}, ensure_ascii=False
        )
    except (TypeError, ValueError):
        encoded_tags = "{}"
    if len(encoded_tags) > 10000:
        encoded_tags = "{}"  # Never persist truncated, invalid JSONB.
    return {
        "source_url": source,
        "category": category,
        "name": str(point.get("name") or "Ressource OSM")[:160],
        "lat": lat, "lon": lon,
        "water_status": str(point.get("water_status") or point.get("status") or "unverified")[:40],
        "tags": encoded_tags,
    }


def _route_wkt(result: dict[str, Any]) -> str | None:
    coords = ((result.get("route_preview") or {}).get("coords") or [])
    if not isinstance(coords, list):
        return None
    clean = []
    for item in coords:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            lat, lon = float(item[0]), float(item[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and 41 <= lat <= 52 and -6 <= lon <= 11):
            continue
        if not clean or (lat, lon) != clean[-1]:
            clean.append((lat, lon))
    if len(clean) < 2:
        return None
    # PostgreSQL handles the route as one indexed geography corridor query;
    # reducing its shape prevents enormous route payloads from monopolizing DB.
    if len(clean) > 1000:
        indices = sorted({round(i * (len(clean) - 1) / 999) for i in range(1000)})
        clean = [clean[i] for i in indices]
    return "SRID=4326;LINESTRING(" + ",".join(f"{lon:.6f} {lat:.6f}" for lat, lon in clean) + ")"


def read_near_route(
    result: dict[str, Any],
    intent: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read only recently evidenced OSM objects; never interpret misses as no POIs."""
    started = time.monotonic()
    if diagnostics is not None:
        diagnostics.update(status="not_attempted", count=0)
    requested = []
    if intent.get("food"):
        requested.append("food")
    if intent.get("water"):
        requested.append("water")
    if intent.get("sleep"):
        requested.extend(("camping", "refuge", "lodging"))
    wkt = _route_wkt(result)
    if not requested or not wkt or os.getenv("TREKBRAIN_OSM_CACHE", "1") == "0":
        return []
    try:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SET LOCAL statement_timeout = '1100ms'"))
            rows = db.execute(text("""
                SELECT source_url, category, name, lat, lon, water_status, osm_tags
                FROM trekbrain_osm_cache_v9
                WHERE category = ANY(:categories)
                  AND last_seen >= NOW() - INTERVAL '10 days'
                  AND ST_DWithin(location, ST_GeogFromText(:route), 6500)
                ORDER BY last_seen DESC
                LIMIT :max_rows
            """), {
                "categories": requested, "route": wkt,
                "max_rows": MAX_LOADED_PER_PLAN,
            }).mappings().all()
        finally:
            db.close()
    except Exception:
        if diagnostics is not None:
            diagnostics["status"] = "unavailable"
        return []
    # For every cached item, the outer resource overlay performs the final
    # precise distance-to-walked-segment and daily-stage check.
    out = []
    for row in rows:
        point = dict(row)
        if not _candidate(point):
            continue
        point.pop("osm_tags", None)
        point["notes"] = "Référence OpenStreetMap mise en cache ; ouverture et disponibilité à vérifier."
        point["_cached_osm"] = True
        out.append(point)
    if diagnostics is not None:
        diagnostics.update(
            status="hit" if out else "miss", count=len(out),
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
    return out


def store_sourced(
    items: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> int:
    """Upsert positive, fresh OSM evidence only; no negative caching or TTL renewal on reads."""
    if diagnostics is not None:
        diagnostics.update(stored=0, status="not_attempted")
    if os.getenv("TREKBRAIN_OSM_CACHE", "1") == "0":
        return 0
    deduped = {}
    for item in items or []:
        if not isinstance(item, dict) or item.get("_cached_osm"):
            continue
        row = _candidate(item)
        if row:
            deduped[row["source_url"]] = row
        if len(deduped) >= MAX_STORED_PER_PLAN:
            break
    if not deduped:
        return 0
    try:
        from .database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SET LOCAL statement_timeout = '1400ms'"))
            stmt = text("""
                INSERT INTO trekbrain_osm_cache_v9
                    (source_url, category, name, lat, lon, water_status, osm_tags, location, last_seen)
                VALUES (:source_url, :category, :name, :lat, :lon,
                        :water_status, CAST(:tags AS JSONB),
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        NOW())
                ON CONFLICT (source_url) DO UPDATE SET
                    category = EXCLUDED.category,
                    name = EXCLUDED.name,
                    lat = EXCLUDED.lat,
                    lon = EXCLUDED.lon,
                    water_status = EXCLUDED.water_status,
                    osm_tags = EXCLUDED.osm_tags,
                    location = EXCLUDED.location,
                    last_seen = NOW()
            """)
            db.execute(stmt, list(deduped.values()))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception:
        if diagnostics is not None:
            diagnostics["status"] = "unavailable"
        return 0
    if diagnostics is not None:
        diagnostics.update(status="stored", stored=len(deduped))
    return len(deduped)


__all__ = ["read_near_route", "store_sourced", "FRESH_DAYS"]
