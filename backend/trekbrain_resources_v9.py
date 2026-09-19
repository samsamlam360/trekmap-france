"""TrekBrain v9 resource and geographic-safety overlay.

Adds route-relative map resources (water, campsites, refuges and public
transport), keeps island planning inside the requested island, and refuses to
show or save a route that was not actually validated by the walking router.
"""
from __future__ import annotations

import json
import math
from typing import Any

from fastapi import Body, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text

from . import smart_planner_v7 as v7
from .trekbrain_geo_safety_v9 import (
    activate_region,
    install_geo_filters,
    reset_region,
    route_safety_report,
    safety_error_message,
)


RESOURCE_LIMITS = {
    "water": 2.8,
    "camping": 4.0,
    "refuge": 4.0,
    "station": 12.0,
    "transport": 8.0,
    "trail": 2.2,
}


class AIRedrawPayload(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(default="medium", max_length=20)
    description: str = Field(default="", max_length=10000)
    duration_days: float | None = Field(default=None, ge=0.25, le=365)
    coords: list[list[float]] = Field(min_length=2, max_length=100)


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _point(item: dict[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(item, dict):
        return None
    lat, lon = _number(item.get("lat")), _number(item.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _route_match(coords: list[list[float]], item: dict[str, Any]) -> tuple[float, float] | None:
    target = _point(item)
    if not target or not coords:
        return None
    stride = max(1, len(coords) // 800)
    best_d, best_i = float("inf"), 0
    for i in range(0, len(coords), stride):
        if not isinstance(coords[i], (list, tuple)) or len(coords[i]) < 2:
            continue
        p = (_number(coords[i][0]), _number(coords[i][1]))
        if p[0] is None or p[1] is None:
            continue
        d = _distance_km(target, (p[0], p[1]))
        if d < best_d:
            best_d, best_i = d, i
    if coords and (len(coords) - 1) % stride:
        last = coords[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            lat, lon = _number(last[0]), _number(last[1])
            if lat is not None and lon is not None:
                d = _distance_km(target, (lat, lon))
                if d < best_d:
                    best_d, best_i = d, len(coords) - 1
    if not math.isfinite(best_d):
        return None
    return best_d, best_i / max(1, len(coords) - 1)


def _resource_kind(item: dict[str, Any], fallback: str = "") -> str:
    raw = f"{item.get('type') or ''} {item.get('category') or ''} {item.get('name') or ''} {fallback}".casefold()
    if fallback == "water" or any(x in raw for x in ("eau", "fontaine", "source")):
        return "water"
    if any(x in raw for x in ("camping", "camp_site", "caravan_site", "campement")):
        return "camping"
    if any(x in raw for x in ("refuge", "abri", "gîte", "gite", "hut")):
        return "refuge"
    if any(x in raw for x in ("gare", "station ferroviaire", "train", "sncf")):
        return "station"
    if fallback == "transport" or any(x in raw for x in ("transport", "bus", "arrêt", "arret")):
        return "transport"
    if any(x in raw for x in ("itinéraire balisé", "itineraire balise", "gr ", "gr®", "sentier")):
        return "trail"
    return fallback or "poi"


def _candidate_resources(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for w in result.get("water") or []:
        if isinstance(w, dict):
            items.append({**w, "kind": "water", "type": "Point d'eau", "notes": w.get("notes") or "Potabilité à vérifier."})
    for a in result.get("accommodations") or []:
        if isinstance(a, dict):
            kind = _resource_kind(a, "refuge")
            items.append({**a, "kind": kind, "notes": a.get("notes") or "Ouverture et disponibilité à vérifier."})
    for p in result.get("points_of_interest") or []:
        if not isinstance(p, dict):
            continue
        kind = _resource_kind(p)
        if kind in {"station", "transport", "trail"}:
            items.append({**p, "kind": kind, "notes": p.get("notes") or "Donnée cartographique ; conditions actuelles à vérifier."})
    return items


def enrich_resources(result: dict[str, Any]) -> dict[str, Any]:
    route = result.get("route_preview") or {}
    coords = route.get("coords") or []
    days = max(1, int(result.get("duration_days") or len(result.get("stages") or []) or 1))
    prepared, seen = [], set()
    for item in _candidate_resources(result):
        point = _point(item)
        if not point:
            continue
        kind = str(item.get("kind") or "poi")
        match = _route_match(coords, item)
        if not match:
            continue
        distance, progress = match
        limit = RESOURCE_LIMITS.get(kind, 4.0)
        if distance > limit:
            continue
        key = (kind, round(point[0], 5), round(point[1], 5), str(item.get("name") or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        route_day = min(days, max(1, int(math.floor(progress * days)) + 1))
        prepared.append({
            "name": str(item.get("name") or "Point")[:160],
            "kind": kind,
            "type": str(item.get("type") or kind)[:80],
            "lat": round(point[0], 6),
            "lon": round(point[1], 6),
            "route_day": route_day,
            "distance_to_route_km": round(distance, 2),
            "status": str(item.get("status") or "")[:80],
            "notes": str(item.get("notes") or "")[:500],
            "source_url": str(item.get("source_url") or "")[:1000],
        })

    priority = {"water": 0, "camping": 1, "refuge": 2, "station": 3, "transport": 4, "trail": 5}
    prepared.sort(key=lambda x: (x["route_day"], priority.get(x["kind"], 9), x["distance_to_route_km"], x["name"]))

    # Avoid a carpet of icons: keep the closest few of each category per day.
    limited, buckets = [], {}
    per_day_caps = {"water": 3, "camping": 2, "refuge": 2, "station": 2, "transport": 3, "trail": 2}
    for item in prepared:
        bucket = (item["route_day"], item["kind"])
        count = buckets.get(bucket, 0)
        if count >= per_day_caps.get(item["kind"], 2):
            continue
        buckets[bucket] = count + 1
        limited.append(item)
        if len(limited) >= 48:
            break

    counts = {k: 0 for k in ("water", "camping", "refuge", "station", "transport", "trail")}
    for item in limited:
        if item["kind"] in counts:
            counts[item["kind"]] += 1

    transport = result.setdefault("transport", {})
    start, end = _point(result.get("start")), _point(result.get("end"))
    mobility = [x for x in limited if x["kind"] in {"station", "transport"}]
    if start and mobility:
        transport["outbound_point"] = min(mobility, key=lambda x: _distance_km(start, (x["lat"], x["lon"])))
    if end and mobility:
        transport["return_point"] = min(mobility, key=lambda x: _distance_km(end, (x["lat"], x["lon"])))

    trails = [x for x in limited if x["kind"] == "trail"]
    result["trail_context"] = {
        "near_route": trails,
        "note": "Les noms de sentiers sont des repères cartographiques proches du tracé. TrekBrain ne prétend pas suivre intégralement un GR sans géométrie de relation vérifiée.",
    }
    result["map_resources"] = {
        "version": "v9.2",
        "points": limited,
        "counts": counts,
        "route_filtered": True,
        "meaning": "Points cartographiques proches d'un tracé pédestre validé. Horaires, ouverture, débit et disponibilité restent à vérifier avant le départ.",
    }
    return result


def _install_plan_overlay(app, legacy_main):
    original = next((r for r in app.router.routes if getattr(r, "path", None) == "/ai/plan" and "POST" in getattr(r, "methods", set())), None)
    if not original:
        raise RuntimeError("Route /ai/plan TrekBrain introuvable pour l'overlay ressources.")
    original_endpoint = original.endpoint
    app.router.routes = [r for r in app.router.routes if r is not original]

    @app.post("/ai/plan")
    def plan_with_resources(
        data: v7.v5.v3.AIPlanRequest = Body(...),
        user=Depends(legacy_main.current_user),
    ):
        # Candidate discovery becomes island-aware for the duration of this
        # request. The ContextVar keeps concurrent requests isolated.
        token = activate_region(data.region or "")
        try:
            result = original_endpoint(data, user)
            if not isinstance(result, dict):
                return result

            report = route_safety_report(result, data)
            if not report["safe"]:
                # Never expose ORS fallback points as a hiking line. A clear
                # refusal is much safer than a convincing-looking route at sea.
                raise HTTPException(status_code=422, detail=safety_error_message(report))

            result["route_safety"] = report
            result.setdefault("advisor_notes", []).insert(
                0,
                "🛡️ Sécurité géographique : tracé pédestre validé avant affichage. Les lignes directes de secours sont interdites dans le conseiller.",
            )
            return enrich_resources(result)
        finally:
            reset_region(token)


def _install_redraw_endpoint(app, legacy_main):
    @app.put("/treks/{trek_id}/ai-redraw")
    def ai_redraw(trek_id: int, data: AIRedrawPayload, user=Depends(legacy_main.current_user)):
        error = legacy_main.validate_coords(data.coords)
        if error:
            raise HTTPException(status_code=400, detail=error)

        route = legacy_main.get_route(data.coords)
        coords = route.get("coords") or []
        report = route_safety_report({
            "route_preview": {
                "coords": coords,
                "distance_km": route.get("distance"),
                "fallback": route.get("fallback"),
            }
        })
        if not report["safe"]:
            raise HTTPException(
                status_code=422,
                detail="Mise à jour refusée : le moteur pédestre n'a pas validé ce tracé. Aucun segment direct de secours ne sera enregistré.",
            )

        db = legacy_main.db_or_503()
        try:
            row = db.execute(text("SELECT owner_id,is_public FROM treks WHERE id=:id"), {"id": trek_id}).first()
            if not row:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not legacy_main.can_manage(row.owner_id, user):
                raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce trek.")
            name = legacy_main.normalize_text(data.name)[:160]
            region = legacy_main.normalize_text(data.region)[:120]
            days = round(float(data.duration_days), 2) if data.duration_days is not None else legacy_main.estimate_duration_days(route["distance"])
            db.execute(text("""
                UPDATE treks
                SET name=:name,region=:region,difficulty=:difficulty,description=:description,
                    distance=:distance,elevation=:elevation,geom=ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),
                    duration_days=:days,duration_minutes=:minutes
                WHERE id=:id
            """), {
                "name": name, "region": region, "difficulty": legacy_main.difficulty(data.difficulty),
                "description": legacy_main.normalize_text(data.description)[:10000],
                "distance": route["distance"], "elevation": legacy_main.elevation_gain(coords),
                "geo": json.dumps(legacy_main.coords_to_geojson(coords)), "days": days,
                "minutes": legacy_main.duration_minutes(days), "id": trek_id,
            })
            db.commit()
            return {
                "message": "Trek recalculé et mis à jour",
                "id": trek_id,
                "distance": route["distance"],
                "duration_days": days,
                "coords": coords,
                "fallback": False,
                "route_safety": report,
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="Mise à jour du tracé momentanément indisponible.") from exc
        finally:
            db.close()


def install_resource_overlay(app, legacy_main):
    # Apply once to v3 candidate discovery. The wrappers are inert unless an
    # island-aware request activates bounds in the current request context.
    install_geo_filters(v7.v5.v3)
    _install_plan_overlay(app, legacy_main)
    _install_redraw_endpoint(app, legacy_main)
