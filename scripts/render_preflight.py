"""Fail fast with readable diagnostics before Render starts TrekMap.

This script is deployment-only. It does not call external routing, Gemini,
Overpass, or modify the database. It validates the Render environment and
imports the production ASGI app so configuration/import errors are caught
during build instead of surfacing as an opaque boot failure.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from urllib.parse import urlparse


def fail(message: str) -> None:
    raise SystemExit(f"[Render preflight] ERREUR: {message}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    required_files = [
        root / "backend" / "app_v5.py",
        root / "frontend" / "index.html",
        root / "requirements.txt",
        root / "render.yaml",
    ]
    missing = [str(path.relative_to(root)) for path in required_files if not path.exists()]
    if missing:
        fail("fichier(s) indispensable(s) absent(s): " + ", ".join(missing))

    production = os.getenv("TREKMAP_ENV", "").strip().lower() in {"prod", "production"}
    if not production:
        fail("TREKMAP_ENV doit valoir 'production' sur Render.")

    origins = os.getenv("FRONTEND_ORIGINS", "").strip()
    if not origins:
        fail("FRONTEND_ORIGINS est absent.")
    for origin in [item.strip() for item in origins.split(",") if item.strip()]:
        if not origin.startswith("https://"):
            fail(f"FRONTEND_ORIGINS contient une origine non HTTPS: {origin}")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        fail(
            "DATABASE_URL est absent. Le service web doit être relié à la base "
            "Render 'trekmap-france-db' (fromDatabase dans render.yaml)."
        )
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg2"}:
        fail(f"DATABASE_URL n'est pas une URL PostgreSQL reconnue ({parsed.scheme!r}).")
    if not parsed.hostname or not parsed.path.strip("/"):
        fail("DATABASE_URL est incomplète (hôte ou nom de base manquant).")

    trekbrain = os.getenv("TREKBRAIN_VERSION", "v8").strip().casefold()
    if trekbrain not in {"v8", "v9"}:
        fail(f"TREKBRAIN_VERSION invalide: {trekbrain!r}")

    import backend.app_v5 as app_v5

    routes = [route.path for route in app_v5.app.routes]
    required_routes = {
        "/",
        "/health/ready",
        "/ai/status",
        "/ai/plan",
        "/ai/clarify",
        "/ai/feedback",
        "/treks/{trek_id}/ai-redraw",
    }
    missing_routes = sorted(required_routes.difference(routes))
    if missing_routes:
        fail("route(s) critique(s) absente(s): " + ", ".join(missing_routes))
    duplicate_routes = sorted(path for path in required_routes if routes.count(path) != 1)
    if duplicate_routes:
        fail("route(s) critique(s) dupliquée(s): " + ", ".join(duplicate_routes))

    if app_v5.TREKBRAIN_VERSION != trekbrain:
        fail(
            f"TrekBrain chargé en {app_v5.TREKBRAIN_VERSION!r} alors que "
            f"TREKBRAIN_VERSION={trekbrain!r}."
        )

    print(
        "[Render preflight] OK | "
        f"Python {platform.python_version()} | "
        f"TrekBrain {app_v5.TREKBRAIN_VERSION} | "
        f"{len(routes)} routes"
    )


if __name__ == "__main__":
    main()
