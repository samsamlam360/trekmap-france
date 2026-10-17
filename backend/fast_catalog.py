"""Fast catalog payload for initial map paint.

No route geometries are sent in the first response. Public metadata and the
signed-in user's allowed private treks are fetched with one lean SQL query.
"""
from fastapi import Depends, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import main as core


def install_fast_catalog(app, db_factory):
    app.add_middleware(GZipMiddleware, minimum_size=900, compresslevel=4)

    @app.get("/catalog/bootstrap")
    def catalog_bootstrap(user=Depends(core.get_optional_user)):
        db=db_factory()
        try:
            uid=user["id"] if user else -1
            rows=db.execute(text("""
                SELECT t.id,t.name,t.region,t.difficulty,t.distance,t.elevation,
                       t.description,t.owner_id,t.is_public,t.view_count,
                       t.duration_minutes,t.duration_days,
                       u.username AS owner_username,
                       (SELECT COUNT(*) FROM trek_favorites f WHERE f.trek_id=t.id)
                           AS favorite_count,
                       NULL::text AS geojson
                FROM treks t LEFT JOIN users u ON u.id=t.owner_id
                WHERE t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE
                ORDER BY t.is_public DESC,favorite_count DESC,t.view_count DESC,t.name ASC
            """),{"uid":uid,"admin":bool(user and user["is_admin"])}).fetchall()
            favorites=set()
            if user:
                favorites={int(r.trek_id) for r in db.execute(text(
                    "SELECT trek_id FROM trek_favorites WHERE user_id=:uid"),
                    {"uid":uid}).fetchall()}
            treks=[core.row_to_dict(row, int(row.id) in favorites) for row in rows]
            # The existing regions API remains unchanged. Client can derive region
            # names from the already-authorized catalog without waiting for another RTT.
            region_counts={}
            for item in treks:
                if item["is_public"]:
                    name=item["region"]
                    region_counts[name]=region_counts.get(name,0)+1
            regions=[{"name":name,"count":count} for name,count in sorted(region_counts.items())]
            return {"treks":treks,"regions":regions}
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(status_code=503,detail="Catalogue temporairement indisponible.") from exc
        finally:
            db.close()
