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
    from .smart_planner_v8 import install_smart_planner

install_smart_planner(app, legacy_main)
if TREKBRAIN_VERSION == "v9":
    # V9 architecture, in order:
    # 1) understand hiking relations;
    # 2) allow short campsite branches;
    # 3) synthesize loops from several walking corridors;
    # 4) solve overnight choices on a real ORS walking-distance matrix;
    # 5) interpret a daily-km value as a target unless explicit bounds are given;
    # 6) trim redundant expensive hypotheses and bound network timeouts;
    # 7) stop retry storms when a public service has just timed out;
    # 8) recover simple loops directly with ORS if the advanced solver fails;
    # 9) surface the real geographic/routing error instead of a generic 422.
    from . import smart_planner_v7 as _planner_v7
    from . import smart_planner_v5 as _planner_v5
    from . import smart_planner_v9 as _planner_v9
    from . import trekbrain_gr_v9 as _gr_v9
    from . import trekbrain_network_v9 as _network_v9
    from . import trekbrain_roundtrip_v9 as _roundtrip_v9
    from . import ors as _ors
    from .trekbrain_gr_v9 import install_gr_guidance
    from .trekbrain_gr_detours_v9 import install_gr_detours
    from .trekbrain_network_v9 import install_path_network
    from .trekbrain_matrix_v9 import install_matrix_planner
    from .trekbrain_distance_tolerance_v9 import install_distance_tolerance
    from .trekbrain_speed_v9 import install_fast_planning
    from .trekbrain_circuit_breaker_v9 import install_circuit_breakers
    from .trekbrain_roundtrip_v9 import install_roundtrip_fallback
    from .trekbrain_failure_diagnostics_v9 import install_failure_diagnostics

    install_gr_guidance(_planner_v7.v5.v3)
    install_gr_detours(_planner_v7.v5.v3, _gr_v9)
    install_path_network(_planner_v7.v5.v3, _gr_v9)
    install_matrix_planner(_planner_v7.v5.v3, _ors, _network_v9)
    install_distance_tolerance(_planner_v7.v5.v3)
    install_fast_planning(_planner_v7.v5.v3, _planner_v5, _planner_v9)
    install_circuit_breakers(_planner_v7.v5.v3, _ors, _roundtrip_v9)
    install_roundtrip_fallback(_planner_v7.v5.v3)
    install_failure_diagnostics(_planner_v7.v5.v3, _planner_v5, _planner_v7)

    # Geographic safety/resources remain final authorities. The request overlay
    # is installed last so natural-language corrections happen before planning.
    from .trekbrain_resources_v9 import install_resource_overlay
    from .trekbrain_request_overlay_v9 import install_request_overlay
    install_resource_overlay(app, legacy_main)
    install_request_overlay(app, legacy_main)

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
