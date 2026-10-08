"""Fail fast with readable diagnostics before Render starts TrekMap.

This script is deployment-only. It does not call external routing, Gemini,
Overpass, or modify the database. It validates the Render environment and
imports the production ASGI app so configuration/import errors are caught
during build instead of surfacing as an opaque boot failure.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def fail(message: str) -> None:
    raise SystemExit(f"[Render preflight] ERREUR: {message}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    # When Render executes `python scripts/render_preflight.py`, Python puts the
    # scripts/ directory at sys.path[0] instead of the repository root. Add the
    # root explicitly so `import backend...` behaves exactly like the Uvicorn
    # start command that Render runs from the repository root.
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

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

    release_channel = os.getenv("TREKBRAIN_RELEASE_CHANNEL", "").strip()
    if production and trekbrain != "v9":
        fail(
            "La production TrekMap est verrouillée sur TrekBrain v9. "
            f"TREKBRAIN_VERSION={trekbrain!r} provoquerait un rollback silencieux."
        )
    if production and release_channel != "v9-stable":
        fail(
            "TREKBRAIN_RELEASE_CHANNEL doit valoir 'v9-stable' sur Render "
            f"(valeur actuelle: {release_channel!r})."
        )

    # Run the network-free TrekBrain regression checks on every production build.
    # These tests exercise the final resource projection and route-first lodging
    # semantics without calling ORS/Overpass/Photon, so they are cheap enough to
    # be a real deployment gate instead of documentation that merely hopes.
    regression_scripts = [
        root / "scripts" / "test_trekbrain_v9.py",
        root / "scripts" / "test_trekbrain_v9_speed.py",
        root / "scripts" / "test_trekbrain_v9_geo_fallback.py",
        root / "scripts" / "test_trekbrain_v9_resources.py",
        root / "scripts" / "test_trekbrain_v9_terrain_recovery.py",
        root / "scripts" / "test_trekbrain_v9_route_logistics.py",
        root / "scripts" / "test_trekbrain_v9_belle_ile_gr340.py",
        root / "scripts" / "test_trekbrain_v9_roundtrip_empty_primary.py",
    ]
    for script in regression_scripts:
        try:
            subprocess.run(
                [sys.executable, str(script)],
                cwd=root,
                check=True,
                timeout=45,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            fail(f"régression TrekBrain détectée dans {script.name}: {exc}")

    if os.getenv("TREKBRAIN_RUN_BENCHMARK", "").strip().casefold() in {"1", "true", "yes", "on"}:
        benchmark = root / "scripts" / "benchmark_trekbrain_v9_render.py"
        try:
            subprocess.run(
                [sys.executable, str(benchmark)],
                cwd=root,
                check=True,
                timeout=180,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            fail(f"benchmark TrekBrain Render interrompu: {exc}")

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

    if trekbrain == "v9":
        status_route = next(
            route
            for route in app_v5.app.routes
            if route.path == "/ai/status" and "GET" in (getattr(route, "methods", None) or set())
        )
        status = status_route.endpoint()
        if not isinstance(status, dict):
            fail("/ai/status ne renvoie pas un objet JSON exploitable.")
        if status.get("release_channel") != "v9-stable":
            fail(f"/ai/status n'annonce pas v9-stable: {status.get('release_channel')!r}")
        if status.get("stability_gate") != "required":
            fail(f"stability_gate invalide: {status.get('stability_gate')!r}")
        if status.get("golden_prompt_count") != 5:
            fail(f"golden_prompt_count invalide: {status.get('golden_prompt_count')!r}")
        if status.get("field_scenario_count") != 40 or status.get("field_suite") != "required":
            fail(
                "La gate terrain v9 doit annoncer 40 scénarios obligatoires "
                f"(count={status.get('field_scenario_count')!r}, suite={status.get('field_suite')!r})."
            )
        if not str(status.get("pipeline_version", "")).startswith("v9-explicit-"):
            fail(f"pipeline_version v9 inattendue: {status.get('pipeline_version')!r}")

    print(
        "[Render preflight] OK | "
        f"Python {platform.python_version()} | "
        f"TrekBrain {app_v5.TREKBRAIN_VERSION} | "
        f"{len(routes)} routes"
    )


if __name__ == "__main__":
    main()
