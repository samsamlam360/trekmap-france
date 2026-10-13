"""Read-only contract check: the production blueprint uses Neon, not the expired Render DB.

No database connection, no HTTP request and no credentials required.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = (ROOT / "render.yaml").read_text(encoding="utf-8")
preflight = (ROOT / "scripts" / "render_preflight.py").read_text(encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")

assert "name: trekmap-france" in config
assert "plan: free" in config
assert "key: TREKBRAIN_RUN_BENCHMARK" in config and 'value: "0"' in config, (
    "Real ORS/Overpass benchmarks must never run inside each Render build"
)
assert "backend.app_v5:app" in config, "Unexpected production entry point"
assert "DB_SSLMODE" in config and "value: require" in config
assert "key: DATABASE_URL" in config and "sync: false" in config
assert "fromDatabase:" not in config, "Production must not point back to Render Postgres"
assert not any(line.lstrip() == "databases:" for line in config.splitlines()), (
    "Do not provision another expiring Render database from the blueprint"
)
assert "trekmap-france-db' (fromDatabase" not in preflight, (
    "Missing DATABASE_URL must guide operators to Neon, not retired Render DB"
)
assert "Neon PostgreSQL/PostGIS" in preflight
assert "Neon" in readme and "backend.app_v5:app" in readme

print("Render/Neon production contract: PASS (blueprint, SSL, secrets, startup, preflight)")
