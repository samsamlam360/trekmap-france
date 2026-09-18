"""Correctifs fonctionnels finaux pour TrekMap France.

Ajoute un index de critères pour la recherche avancée et un stockage durable des
photos de trek dans PostgreSQL. Cette couche reste séparée du backend historique.
"""

from __future__ import annotations

from fastapi import Depends, File, HTTPException, UploadFile, Response
from sqlalchemy import text

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_TREK = 8


def install_functional_upgrade(app, legacy_main, db_factory):
    db = db_factory()
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS trek_photos (
                id SERIAL PRIMARY KEY,
                trek_id INTEGER NOT NULL REFERENCES treks(id) ON DELETE CASCADE,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                filename VARCHAR(255) NOT NULL DEFAULT 'photo',
                media_type VARCHAR(50) NOT NULL,
                data BYTEA NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_trek_photos_trek ON trek_photos(trek_id, created_at, id)"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    def visible_clause(user):
        return user["id"] if user else -1, bool(user and user.get("is_admin"))

    @app.get("/catalog/criteria")
    def catalog_criteria(user=Depends(legacy_main.get_optional_user)):
        """Retourne en une requête les critères enrichis de tous les treks visibles."""
        db = db_factory()
        try:
            uid, admin = visible_clause(user)
            rows = db.execute(text("""
                SELECT t.id,
                       COALESCE(t.route_type,'') AS route_type,
                       COALESCE(t.best_season,'') AS best_season,
                       COALESCE(t.start_name,'') AS start_name,
                       COALESCE(t.end_name,'') AS end_name,
                       COALESCE(t.points_of_interest,'[]'::jsonb) AS points_of_interest,
                       COALESCE(r.average,0) AS rating_average,
                       COALESCE(r.count,0) AS rating_count,
                       COALESCE(p.photo_count,0) AS uploaded_photo_count,
                       COALESCE(jsonb_array_length(t.photos),0) AS external_photo_count
                FROM treks t
                LEFT JOIN (
                    SELECT trek_id, AVG(value)::float AS average, COUNT(*) AS count
                    FROM trek_ratings GROUP BY trek_id
                ) r ON r.trek_id=t.id
                LEFT JOIN (
                    SELECT trek_id, COUNT(*) AS photo_count
                    FROM trek_photos GROUP BY trek_id
                ) p ON p.trek_id=t.id
                WHERE t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE
            """), {"uid": uid, "admin": admin}).mappings().all()
            return {
                "items": [
                    {
                        "id": int(row["id"]),
                        "route_type": row["route_type"],
                        "best_season": row["best_season"],
                        "start_name": row["start_name"],
                        "end_name": row["end_name"],
                        "points_of_interest": list(row["points_of_interest"] or []),
                        "rating_average": round(float(row["rating_average"] or 0), 2),
                        "rating_count": int(row["rating_count"] or 0),
                        "has_photo": int(row["uploaded_photo_count"] or 0) + int(row["external_photo_count"] or 0) > 0,
                    }
                    for row in rows
                ]
            }
        finally:
            db.close()

    @app.post("/treks/{trek_id}/photos")
    async def upload_trek_photo(
        trek_id: int,
        file: UploadFile = File(...),
        user=Depends(legacy_main.current_user),
    ):
        db = db_factory()
        try:
            trek = db.execute(text("SELECT owner_id FROM treks WHERE id=:id"), {"id": trek_id}).first()
            if not trek:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not legacy_main.can_manage(trek.owner_id, user):
                raise HTTPException(status_code=403, detail="Tu ne peux pas ajouter de photo à ce trek.")
            media_type = (file.content_type or "").lower().strip()
            if media_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail="Format d’image accepté : JPG, PNG ou WEBP.")
            count = db.execute(text("SELECT COUNT(*) FROM trek_photos WHERE trek_id=:id"), {"id": trek_id}).scalar() or 0
            if int(count) >= MAX_IMAGES_PER_TREK:
                raise HTTPException(status_code=400, detail=f"Maximum {MAX_IMAGES_PER_TREK} photos par trek.")

            data = bytearray()
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise HTTPException(status_code=413, detail="La photo dépasse 8 Mo.")
            if not data:
                raise HTTPException(status_code=400, detail="La photo est vide.")
            filename = (file.filename or "photo")[:255]
            photo_id = db.execute(text("""
                INSERT INTO trek_photos(trek_id,owner_id,filename,media_type,data)
                VALUES(:t,:u,:f,:m,:d) RETURNING id
            """), {"t": trek_id, "u": user["id"], "f": filename, "m": media_type, "d": bytes(data)}).scalar_one()
            db.commit()
            return {"id": int(photo_id), "url": f"/media/trek-photos/{int(photo_id)}", "filename": filename}
        except HTTPException:
            db.rollback()
            raise
        finally:
            await file.close()
            db.close()

    @app.get("/media/trek-photos/{photo_id}")
    def get_trek_photo(photo_id: int, user=Depends(legacy_main.get_optional_user)):
        db = db_factory()
        try:
            row = db.execute(text("""
                SELECT p.media_type,p.data,t.is_public,t.owner_id
                FROM trek_photos p JOIN treks t ON t.id=p.trek_id
                WHERE p.id=:id
            """), {"id": photo_id}).first()
            if not row:
                raise HTTPException(status_code=404, detail="Photo introuvable.")
            allowed = bool(row.is_public or (user and (user.get("is_admin") or NumberLike(user.get("id")) == NumberLike(row.owner_id))))
            if not allowed:
                raise HTTPException(status_code=404, detail="Photo introuvable.")
            cache = "public, max-age=86400" if row.is_public else "private, no-store"
            return Response(content=bytes(row.data), media_type=row.media_type, headers={"Cache-Control": cache})
        finally:
            db.close()

    @app.delete("/treks/{trek_id}/photos/{photo_id}")
    def delete_trek_photo(trek_id: int, photo_id: int, user=Depends(legacy_main.current_user)):
        db = db_factory()
        try:
            trek = db.execute(text("SELECT owner_id FROM treks WHERE id=:id"), {"id": trek_id}).first()
            if not trek:
                raise HTTPException(status_code=404, detail="Trek introuvable.")
            if not legacy_main.can_manage(trek.owner_id, user):
                raise HTTPException(status_code=403, detail="Tu ne peux pas supprimer cette photo.")
            result = db.execute(text("DELETE FROM trek_photos WHERE id=:p AND trek_id=:t"), {"p": photo_id, "t": trek_id})
            if not result.rowcount:
                raise HTTPException(status_code=404, detail="Photo introuvable.")
            db.commit()
            return {"ok": True}
        except HTTPException:
            db.rollback()
            raise
        finally:
            db.close()

    @app.get("/treks/{trek_id}/uploaded-photos")
    def uploaded_photos(trek_id: int, user=Depends(legacy_main.get_optional_user)):
        db = db_factory()
        try:
            uid, admin = visible_clause(user)
            trek = db.execute(text("""
                SELECT id FROM treks
                WHERE id=:id AND (is_public=TRUE OR owner_id=:uid OR :admin=TRUE)
            """), {"id": trek_id, "uid": uid, "admin": admin}).first()
            if not trek:
                raise HTTPException(status_code=404, detail="Trek introuvable ou privé.")
            rows = db.execute(text("""
                SELECT id,filename,created_at FROM trek_photos
                WHERE trek_id=:id ORDER BY created_at,id
            """), {"id": trek_id}).mappings().all()
            return {
                "photos": [
                    {"id": int(row["id"]), "filename": row["filename"], "url": f"/media/trek-photos/{int(row['id'])}"}
                    for row in rows
                ]
            }
        finally:
            db.close()


def NumberLike(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
