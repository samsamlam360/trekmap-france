"""Point d'entrée TrekMap France 5.0.

Cette entrée conserve le backend historique, installe les extensions produit puis
sert directement le frontend construit. L'ancienne couche UI_ENHANCEMENT de
main_production n'est plus injectée : l'interface est désormais pilotée par une
seule couche unifiée générée au build.
"""

from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text

from . import main as legacy_main
from .main_production import app, robust_db_or_503, FRONTEND_FILE
from .product_upgrade import install_product_upgrade
from .functional_upgrade import install_functional_upgrade
from .smart_planner_v7 import install_smart_planner

install_product_upgrade(app, legacy_main, robust_db_or_503)
install_functional_upgrade(app, legacy_main, robust_db_or_503)
install_smart_planner(app, legacy_main)

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
