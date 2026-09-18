"""Extensions produit TrekMap France.

Cette couche garde backend/main.py stable et ajoute les fonctions avancées utilisées
par l'interface 5.0 : notes, informations enrichies, bibliothèque utilisateur et
contrôles de cohérence production.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text


class RatingPayload(BaseModel):
    value: int = Field(ge=1, le=5)


class TrekExtrasPayload(BaseModel):
    route_type: str = Field(default="", max_length=40)
    best_season: str = Field(default="", max_length=120)
    start_name: str = Field(default="", max_length=180)
    end_name: str = Field(default="", max_length=180)
    photos: list[str] = Field(default_factory=list)
    points_of_interest: list[dict[str, Any]] = Field(default_factory=list)


def _clean_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _clean_urls(values: list[str]) -> list[str]:
    out: list[str] = []
    for raw in values[:8]:
        value = str(raw or "").strip()
        if re.fullmatch(r"https://[^\s]{1,1000}", value):
            out.append(value)
    return out


def _clean_pois(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in values[:30]:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"), 120)
        if not name:
            continue
        clean: dict[str, Any] = {"name": name, "type": _clean_text(item.get("type"), 60)}
        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                clean["lat"] = round(lat, 7)
                clean["lon"] = round(lon, 7)
        except (TypeError, ValueError):
            pass
        out.append(clean)
    return out


def install_product_upgrade(app, legacy_main, db_factory):
    """Installe les routes de la couche produit sans réécrire main.py."""
    state = {"schema_ready": False}

    def ensure_product_schema():
        if state["schema_ready"]:
            return
        db = db_factory()
        try:
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS route_type VARCHAR(40) NOT NULL DEFAULT ''"))
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS best_season VARCHAR(120) NOT NULL DEFAULT ''"))
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS start_name VARCHAR(180) NOT NULL DEFAULT ''"))
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS end_name VARCHAR(180) NOT NULL DEFAULT ''"))
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb"))
            db.execute(text("ALTER TABLE treks ADD COLUMN IF NOT EXISTS points_of_interest JSONB NOT NULL DEFAULT '[]'::jsonb"))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS trek_ratings (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                    value SMALLINT NOT NULL CHECK(value BETWEEN 1 AND 5),
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(user_id, trek_id)
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_ratings_trek ON trek_ratings(trek_id)"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_treks_region_public ON treks(region,is_public)"))
            db.commit()
            state["schema_ready"] = True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.on_event("startup")
    def product_startup():
        try:
            ensure_product_schema()
            print("[TrekMap 5.0] Extensions produit prêtes")
        except Exception as exc:
            # Le backend historique reste disponible même si la migration produit doit être retentée.
            print("[TrekMap 5.0] Migration produit différée:", repr(exc))

    def visible_trek(db, trek_id: int, user):
        uid = user["id"] if user else -1
        row = db.execute(text("""
            SELECT id,name,owner_id,is_public,route_type,best_season,start_name,end_name,
                   photos,points_of_interest
            FROM treks
            WHERE id=:id AND (is_public=TRUE OR owner_id=:uid OR :admin=TRUE)
        """), {"id": trek_id, "uid": uid, "admin": bool(user and user.get("is_admin"))}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Trek introuvable ou privé.")
        return row

    @app.get("/treks/{trek_id}/extras")
    def trek_extras(trek_id: int, user=Depends(legacy_main.get_optional_user)):
        ensure_product_schema()
        db = db_factory()
        try:
            row = visible_trek(db, trek_id, user)
            rating = db.execute(text("""
                SELECT COUNT(*) count, COALESCE(AVG(value),0) average
                FROM trek_ratings WHERE trek_id=:id
            """), {"id": trek_id}).mappings().one()
            mine = None
            if user:
                mine = db.execute(text("SELECT value FROM trek_ratings WHERE trek_id=:t AND user_id=:u"),
                                  {"t": trek_id, "u": user["id"]}).scalar()
            return {
                "route_type": row["route_type"] or "",
                "best_season": row["best_season"] or "",
                "start_name": row["start_name"] or "",
                "end_name": row["end_name"] or "",
                "photos": list(row["photos"] or []),
                "points_of_interest": list(row["points_of_interest"] or []),
                "rating": {
                    "average": round(float(rating["average"] or 0), 2),
                    "count": int(rating["count"] or 0),
                    "mine": int(mine) if mine is not None else None,
                },
            }
        finally:
            db.close()

    @app.put("/treks/{trek_id}/extras")
    def update_trek_extras(trek_id: int, payload: TrekExtrasPayload,
                           user=Depends(legacy_main.current_user)):
        ensure_product_schema()
        db = db_factory()
        try:
            row = db.execute(text("SELECT owner_id FROM treks WHERE id=:id"), {"id": trek_id}).first()
            if not row:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not legacy_main.can_manage(row.owner_id, user):
                raise HTTPException(status_code=403, detail="Tu ne peux pas modifier ce trek.")
            data = {
                "id": trek_id,
                "route_type": _clean_text(payload.route_type, 40),
                "best_season": _clean_text(payload.best_season, 120),
                "start_name": _clean_text(payload.start_name, 180),
                "end_name": _clean_text(payload.end_name, 180),
                "photos": json.dumps(_clean_urls(payload.photos), ensure_ascii=False),
                "pois": json.dumps(_clean_pois(payload.points_of_interest), ensure_ascii=False),
            }
            db.execute(text("""
                UPDATE treks SET route_type=:route_type,best_season=:best_season,
                    start_name=:start_name,end_name=:end_name,
                    photos=CAST(:photos AS jsonb),points_of_interest=CAST(:pois AS jsonb)
                WHERE id=:id
            """), data)
            db.commit()
            return {"message": "Informations du trek enregistrées."}
        except HTTPException:
            db.rollback()
            raise
        finally:
            db.close()

    @app.put("/treks/{trek_id}/rating")
    def rate_trek(trek_id: int, payload: RatingPayload, user=Depends(legacy_main.current_user)):
        ensure_product_schema()
        db = db_factory()
        try:
            visible_trek(db, trek_id, user)
            db.execute(text("""
                INSERT INTO trek_ratings(user_id,trek_id,value)
                VALUES(:u,:t,:v)
                ON CONFLICT(user_id,trek_id) DO UPDATE
                SET value=EXCLUDED.value,updated_at=CURRENT_TIMESTAMP
            """), {"u": user["id"], "t": trek_id, "v": payload.value})
            db.commit()
            row = db.execute(text("SELECT COUNT(*) count,AVG(value) average FROM trek_ratings WHERE trek_id=:t"),
                             {"t": trek_id}).mappings().one()
            return {"value": payload.value, "average": round(float(row["average"] or 0), 2),
                    "count": int(row["count"] or 0)}
        except HTTPException:
            db.rollback()
            raise
        finally:
            db.close()

    @app.get("/auth/library")
    def user_library(user=Depends(legacy_main.current_user)):
        ensure_product_schema()
        db = db_factory()
        try:
            uid = user["id"]
            mine = db.execute(text("""
                SELECT id,name,region,distance,elevation,is_public,view_count
                FROM treks WHERE owner_id=:u ORDER BY created_at DESC LIMIT 30
            """), {"u": uid}).mappings().all()
            favorites = db.execute(text("""
                SELECT t.id,t.name,t.region,t.distance,t.elevation,t.is_public,t.view_count
                FROM trek_favorites f JOIN treks t ON t.id=f.trek_id
                WHERE f.user_id=:u AND (t.is_public OR t.owner_id=:u)
                ORDER BY f.created_at DESC LIMIT 30
            """), {"u": uid}).mappings().all()
            plans = db.execute(text("""
                SELECT t.id,t.name,t.region,t.distance,p.updated_at
                FROM trek_plans p JOIN treks t ON t.id=p.trek_id
                WHERE p.user_id=:u AND (t.is_public OR t.owner_id=:u)
                ORDER BY p.updated_at DESC LIMIT 30
            """), {"u": uid}).mappings().all()
            ratings = db.execute(text("SELECT COUNT(*) FROM trek_ratings WHERE user_id=:u"), {"u": uid}).scalar() or 0
            return {
                "mine": [dict(x) for x in mine],
                "favorites": [dict(x) for x in favorites],
                "plans": [dict(x) for x in plans],
                "ratings": int(ratings),
            }
        finally:
            db.close()

    @app.get("/health/ready")
    def readiness():
        ensure_product_schema()
        db = db_factory()
        try:
            db.execute(text("SELECT 1")).scalar_one()
            invalid = db.execute(text("""
                SELECT COUNT(*) FROM treks
                WHERE geom IS NOT NULL AND (ST_SRID(geom)<>4326 OR NOT ST_IsValid(geom))
            """)).scalar() or 0
            return {"status": "ok" if int(invalid) == 0 else "degraded", "database": "ok",
                    "invalid_geometries": int(invalid), "version": "5.0"}
        finally:
            db.close()

    @app.get("/admin/consistency")
    def consistency(user=Depends(legacy_main.current_user)):
        ensure_product_schema()
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="Accès administrateur requis.")
        db = db_factory()
        try:
            return {
                "treks_without_geometry": int(db.execute(text("SELECT COUNT(*) FROM treks WHERE geom IS NULL")).scalar() or 0),
                "orphan_favorites": int(db.execute(text("SELECT COUNT(*) FROM trek_favorites f LEFT JOIN treks t ON t.id=f.trek_id WHERE t.id IS NULL")).scalar() or 0),
                "orphan_plans": int(db.execute(text("SELECT COUNT(*) FROM trek_plans p LEFT JOIN treks t ON t.id=p.trek_id WHERE t.id IS NULL")).scalar() or 0),
                "orphan_ratings": int(db.execute(text("SELECT COUNT(*) FROM trek_ratings r LEFT JOIN treks t ON t.id=r.trek_id WHERE t.id IS NULL")).scalar() or 0),
            }
        finally:
            db.close()
