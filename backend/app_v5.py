"""Point d'entrée TrekMap France 5.0.

Cette entrée conserve le backend historique, installe les extensions produit puis
sert directement le frontend construit. L'ancienne couche UI_ENHANCEMENT de
main_production n'est plus injectée : l'interface est désormais pilotée par une
seule couche unifiée générée au build.
"""

import os

from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from . import main as legacy_main
from .main_production import app, robust_db_or_503, FRONTEND_FILE
from .product_upgrade import install_product_upgrade
from .functional_upgrade import install_functional_upgrade

install_product_upgrade(app, legacy_main, robust_db_or_503)
install_functional_upgrade(app, legacy_main, robust_db_or_503)
TREKBRAIN_VERSION = os.getenv("TREKBRAIN_VERSION", "v8").strip().casefold()
if TREKBRAIN_VERSION == "v9":
    from .smart_planner_v9 import install_smart_planner
else:
    # V8 remains the safe production default. V9 is activated explicitly in a
    # staging environment, so an incomplete V9 change cannot replace V8 merely
    # because it was merged or deployed.
    from .smart_planner_v8 import install_smart_planner

install_smart_planner(app, legacy_main)
if TREKBRAIN_VERSION == "v9":
    # GR/GRP relations are strong route evidence: use their real OSM geometry
    # to guide candidate selection before the geographic safety overlay runs.
    # They never bypass pedestrian routing or the final safety gate.
    from . import smart_planner_v7 as _planner_v7
    from .trekbrain_gr_v9 import install_gr_guidance
    install_gr_guidance(_planner_v7.v5.v3)

    # Keep V8 untouched. V9 first adds geographic safety/resources, then wraps
    # the public planner endpoints with natural-language request reconciliation.
    # The reconciliation wrapper is intentionally installed last so stale form
    # regions are corrected before island filtering, research and routing run.
    from .trekbrain_resources_v9 import install_resource_overlay
    from .trekbrain_request_overlay_v9 import install_request_overlay
    install_resource_overlay(app, legacy_main)
    install_request_overlay(app, legacy_main)

# Retire la route production historique qui injectait encore une ancienne couche
# CSS/JS. Même principe pour la route photo : on la remplace par une version qui
# sait aussi servir les images des treks privés à leur propriétaire.
app.router.routes = [
    route for route in app.router.routes
    if route.path not in {"/", "/media/trek-photos/{photo_id}"}
]


@app.get("/", include_in_schema=False)
def unified_root():
    if not FRONTEND_FILE.exists():
        return {"name": "TrekMap France", "version": app.version, "status": "ok"}
    return HTMLResponse(FRONTEND_FILE.read_text(encoding="utf-8"), media_type="text/html")


@app.get("/media/trek-photos/{photo_id}")
def unified_trek_photo(photo_id: int, user=Depends(legacy_main.get_optional_user)):
    db = robust_db_or_503()
    try:
        row = db.execute(text("""
            SELECT p.media_type,p.data,t.is_public,t.owner_id
            FROM trek_photos p
            JOIN treks t ON t.id=p.trek_id
            WHERE p.id=:id
        """), {"id": photo_id}).first()
        if not row:
            raise HTTPException(status_code=404, detail="Photo introuvable.")
        uid = user["id"] if user else -1
        admin = bool(user and user.get("is_admin"))
        if not row.is_public and NumberSafe(row.owner_id) != NumberSafe(uid) and not admin:
            raise HTTPException(status_code=404, detail="Photo introuvable.")
        return Response(
            content=bytes(row.data),
            media_type=row.media_type,
            headers={"Cache-Control": "private, max-age=3600" if not row.is_public else "public, max-age=86400"},
        )
    finally:
        db.close()


def NumberSafe(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
