"""Optional OSM migration must never take down accounts or critical schema."""
from pathlib import Path
import ast
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import main
from scripts import benchmark_trekbrain_v9_production as bench


class FakeDb:
    def __init__(self, fails):
        self.fails = fails
        self.queries = []
        self.did_rollback = False
        self.did_commit = False
        self.did_close = False
    def execute(self, statement, params=None):
        query = str(statement)
        self.queries.append(query)
        if self.fails and "CREATE TABLE IF NOT EXISTS trekbrain_osm_cache_v9" in query:
            raise PermissionError("fake optional schema denied")
        return self
    def commit(self):
        self.did_commit = True
    def rollback(self):
        self.did_rollback = True
    def close(self):
        self.did_close = True


old_factory = main.SessionLocal
old_core = main.SCHEMA_READY
old_cache = main.OSM_CACHE_SCHEMA_READY
try:
    main.SCHEMA_READY = True  # Base schema already committed.
    main.OSM_CACHE_SCHEMA_READY = False
    calls = []
    def fake_factory():
        conn = FakeDb(fails=True)
        calls.append(conn)
        return conn
    main.SessionLocal = fake_factory
    assert main.ensure_osm_cache_schema() is False
    assert main.SCHEMA_READY is True
    assert main.OSM_CACHE_SCHEMA_READY is False
    assert calls[-1].did_rollback and calls[-1].did_close
    # When the optional DB table cannot be created, the user's authentication
    # session must still be available. Failure cannot roll back core schema.
    session = main.db_or_503()
    assert session is calls[-1]
    assert main.SCHEMA_READY is True

    main.OSM_CACHE_SCHEMA_READY = False
    def happy_factory():
        conn = FakeDb(fails=False)
        calls.append(conn)
        return conn
    main.SessionLocal = happy_factory
    assert main.ensure_osm_cache_schema() is True
    assert calls[-1].did_commit and calls[-1].did_close
    assert any("CREATE INDEX IF NOT EXISTS idx_trekbrain_osm_cache_location" in x
               for x in calls[-1].queries)
    assert main.OSM_CACHE_SCHEMA_READY is True
finally:
    main.SessionLocal = old_factory
    main.SCHEMA_READY = old_core
    main.OSM_CACHE_SCHEMA_READY = old_cache

# The critical migration can no longer contain optional cache DDL.
tree = ast.parse((ROOT / "backend/main.py").read_text(encoding="utf-8"))
core = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
            and x.name == "ensure_schema")
optional = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                and x.name == "ensure_osm_cache_schema")
assert "CREATE TABLE IF NOT EXISTS trekbrain_osm_cache_v9" not in ast.unparse(core)
assert "CREATE TABLE IF NOT EXISTS trekbrain_osm_cache_v9" in ast.unparse(optional)
assert "ensure_osm_cache_schema()" in ast.unparse(core)

# Zero-hit cache metrics are a cold visit only on successful 'miss' response.
# A database outage must never be mislabelled a successful cold search.
plan = {
    "map_resources": {"coverage": {"food": "not_verified"}},
    "route_preview": {"coords": [[45.0, 5.0], [45.01, 5.01]]},
    "stages": [{"day": 1, "distance_km": 1.4}],
    "duration_days": 1,
    "start": {"lat": 45.0, "lon": 5.0},
    "end": {"lat": 45.01, "lon": 5.01},
}
code = (ROOT / "scripts/benchmark_trekbrain_v9_production.py").read_text(encoding="utf-8")
assert 'cache_context.get("status") == "miss"' in code
assert '"POSTGRES_UNAVAILABLE:' in code
assert '"GET", "/health/ready"' in code
assert '"cold_cache": cold_cache' in code
print("TrekBrain schema isolation, optional PostGIS migration and honest cold-cache telemetry: PASS")
