"""Save an existing TrekBrain pedestrian geometry without routing it a second time.

The user must be authenticated.  New treks remain private.  Updates can modify
only a trek owned by the user (or administered by an admin).  Uses existing
treks/PostGIS schema, no migrations, no ORS, no terrain or elevation queries.
"""
from __future__ import annotations

import json
import math
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

# Bound the JSON geometry independently of much larger GPX uploads.
MAX_AI_ROUTE_POINTS = 50000
STORED_AI_ROUTE_POINTS = 12000


class TrekBrainGeometryPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(default="medium", max_length=20)
    description: str = Field(default="", max_length=10000)
    duration_days: float | None = Field(default=None, ge=0.25, le=365)
    coords: list[list[float]] = Field(min_length=2, max_length=MAX_AI_ROUTE_POINTS)
    elevation_m: float | None = Field(default=None, ge=0, le=100000)


def _prepared_geometry(data: TrekBrainGeometryPayload, legacy_main: Any):
    """Validate lat/lon and preserve the already routed line; never snap/reroute."""
    if not isinstance(data.coords, list) or not 2 <= len(data.coords) <= MAX_AI_ROUTE_POINTS:
        raise HTTPException(status_code=422, detail="Le tracé TrekBrain doit contenir au moins deux points GPS.")
    coords = []
    distinct = False
    last = None
    for candidate in data.coords:
        if not isinstance(candidate, list) or len(candidate) != 2:
            raise HTTPException(status_code=422, detail="Un point GPS du tracé est incomplet.")
        lat, lon = candidate
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (lat, lon)):
            raise HTTPException(status_code=422, detail="Le tracé contient des coordonnées GPS invalides.")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise HTTPException(status_code=422, detail="Le tracé contient des coordonnées GPS hors limites.")
        point = [float(lat), float(lon)]
        if last is not None and point != last:
            distinct = True
        if point != last:
            coords.append(point)
        last = point
    if not distinct or len(coords) < 2:
        raise HTTPException(status_code=422, detail="Le tracé TrekBrain ne contient pas deux positions distinctes.")
    distance = legacy_main.distance_gps(coords)
    if not math.isfinite(distance) or distance <= 0:
        raise HTTPException(status_code=422, detail="Le tracé TrekBrain est trop court pour être enregistré.")
    # Like imported GPX tracks, preserve full measured distance while bounding
    # only the stored polyline density for fast database/map rendering.
    stored, simplified = legacy_main.simplify_gpx_coords(coords, max_points=STORED_AI_ROUTE_POINTS)
    if len(stored) < 2:
        raise HTTPException(status_code=422, detail="La trace GPS n'est pas exploitable.")
    days = round(float(data.duration_days), 2) if data.duration_days is not None else legacy_main.estimate_duration_days(distance)
    gain = round(float(data.elevation_m)) if data.elevation_m is not None else 0
    return {
        "name": legacy_main.normalize_text(data.name)[:160],
        "region": legacy_main.normalize_text(data.region)[:120],
        "difficulty": legacy_main.difficulty(data.difficulty),
        "description": legacy_main.normalize_text(data.description)[:10000],
        "duration_days": days,
        "duration_minutes": legacy_main.duration_minutes(days),
        "distance": distance,
        "elevation": gain,
        "geo": json.dumps(legacy_main.coords_to_geojson(stored)),
        "points_original": len(data.coords),
        "points_stored": len(stored),
        "simplified": simplified,
    }


def install_trekbrain_route_persistence(app, legacy_main, db_factory):
    @app.post("/treks/ai-save", status_code=201)
    def create_trekbrain_route(payload: TrekBrainGeometryPayload, user=Depends(legacy_main.current_user)):
        values = _prepared_geometry(payload, legacy_main)
        if not values["name"] or not values["region"]:
            raise HTTPException(status_code=422, detail="Un nom et une région sont nécessaires.")
        db = db_factory()
        try:
            result = db.execute(text("""
                INSERT INTO treks(name,region,difficulty,distance,elevation,description,
                                  geom,owner_id,is_public,duration_days,duration_minutes)
                VALUES(:name,:region,:difficulty,:distance,:elevation,:description,
                       ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),:owner,FALSE,:duration_days,:duration_minutes)
                RETURNING id
            """), {**values, "owner": int(user["id"])}).scalar_one()
            db.commit()
            return {
                "id": int(result),
                "message": "TrekBrain enregistré en privé sans recalcul du tracé.",
                "distance": values["distance"],
                "duration_days": values["duration_days"],
                "points_original": values["points_original"],
                "points_stored": values["points_stored"],
                "route_source": "existing-trekbrain-geometry",
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail="Impossible d'enregistrer le trek TrekBrain.") from exc
        finally:
            db.close()

    @app.put("/treks/{trek_id}/ai-geometry")
    def update_trekbrain_route(trek_id: int, payload: TrekBrainGeometryPayload,
                              user=Depends(legacy_main.current_user)):
        values = _prepared_geometry(payload, legacy_main)
        if not values["name"] or not values["region"]:
            raise HTTPException(status_code=422, detail="Un nom et une région sont nécessaires.")
        db = db_factory()
        try:
            row = db.execute(
                text("SELECT id,owner_id FROM treks WHERE id=:id"),
                {"id": int(trek_id)},
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not user.get("is_admin") and (row.owner_id is None or int(row.owner_id) != int(user["id"])):
                raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce trek.")
            db.execute(text("""
                UPDATE treks
                SET name=:name,region=:region,difficulty=:difficulty,distance=:distance,
                    elevation=:elevation,description=:description,
                    geom=ST_SetSRID(ST_GeomFromGeoJSON(:geo),4326),
                    duration_days=:duration_days,duration_minutes=:duration_minutes
                WHERE id=:id
            """), {**values, "id": int(trek_id)})
            db.commit()
            return {
                "id": int(trek_id),
                "message": "Tracé existant mis à jour sans recalcul ni doublon.",
                "distance": values["distance"],
                "points_original": values["points_original"],
                "points_stored": values["points_stored"],
                "route_source": "existing-trekbrain-geometry",
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail="Impossible de mettre à jour le trek.") from exc
        finally:
            db.close()
