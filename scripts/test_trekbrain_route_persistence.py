"""Offline regression: TrekBrain saves its actual polyline without ORS or Neon.

Simulates authenticated create/update and validates owner access, geometry
format, excessive point counts and that no external provider is touched.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from backend.trekbrain_route_persistence_v9 import (
    MAX_AI_ROUTE_POINTS,
    STORED_AI_ROUTE_POINTS,
    TrekBrainGeometryPayload,
    _prepared_geometry,
    install_trekbrain_route_persistence,
)


class FakeLegacy:
    @staticmethod
    def current_user():
        raise AssertionError("The endpoint must be protected by a FastAPI user dependency.")

    @staticmethod
    def distance_gps(coords):
        return round(sum(
            math.hypot(b[0] - a[0], b[1] - a[1]) * 111
            for a, b in zip(coords, coords[1:])
        ), 2)

    @staticmethod
    def simplify_gpx_coords(coords, max_points=12000):
        assert max_points == STORED_AI_ROUTE_POINTS
        if len(coords) <= max_points:
            return coords, False
        return coords[::5] + [coords[-1]], True

    @staticmethod
    def normalize_text(value):
        return str(value).strip()

    @staticmethod
    def difficulty(value):
        return value if value in ("easy", "medium", "hard") else "medium"

    @staticmethod
    def estimate_duration_days(distance):
        return 1 if distance <= 20 else 3

    @staticmethod
    def duration_minutes(days):
        return int(days * 1440)

    @staticmethod
    def coords_to_geojson(coords):
        return {"type": "LineString", "coordinates": [[p[1], p[0]] for p in coords]}

    @staticmethod
    def get_route(_):
        raise AssertionError("A second ORS route request must never occur.")

    @staticmethod
    def elevation_gain(_):
        raise AssertionError("An external elevation request must never occur.")


class FakeResult:
    def __init__(self, owner_id=11, exists=True):
        self.owner_id = owner_id
        self.exists = exists

    def scalar_one(self):
        return 739

    def first(self):
        return SimpleNamespace(id=739, owner_id=self.owner_id) if self.exists else None


class FakeDatabase:
    def __init__(self, owner_id=11):
        self.owner_id = owner_id
        self.exists = True
        self.statements = []
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def execute(self, sql, params):
        self.statements.append((str(sql), params))
        return FakeResult(owner_id=self.owner_id, exists=self.exists)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1


def expect_http(status, callback):
    try:
        callback()
    except HTTPException as error:
        assert error.status_code == status, (error.status_code, error.detail)
    else:
        raise AssertionError(f"Expected HTTP {status}")


plan = TrekBrainGeometryPayload(
    name="Boucle du Vercors",
    region="Auvergne-Rhône-Alpes",
    difficulty="medium",
    duration_days=3,
    elevation_m=1150,
    coords=[[45.00, 5.00], [45.01, 5.04], [45.02, 5.05], [45.02, 5.05], [45.01, 5.00]],
)

ready = _prepared_geometry(plan, FakeLegacy)
assert ready["distance"] > 0
assert ready["elevation"] == 1150
assert ready["points_stored"] == 4
assert ready["points_original"] == 5
assert ready["duration_days"] == 3
assert json.loads(ready["geo"])["coordinates"][0] == [5.0, 45.0]
assert json.loads(ready["geo"])["coordinates"][-1] == [5.0, 45.01]

app = FastAPI()
db = FakeDatabase()
install_trekbrain_route_persistence(app, FakeLegacy, lambda: db)
create = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/treks/ai-save")
update = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/treks/{trek_id}/ai-geometry")
assert {"POST"} <= next(r.methods for r in app.routes if getattr(r, "path", None) == "/treks/ai-save")
assert {"PUT"} <= next(r.methods for r in app.routes if getattr(r, "path", None) == "/treks/{trek_id}/ai-geometry")

created = create(plan, user={"id": 11, "is_admin": False})
assert created["id"] == 739
assert created["route_source"] == "existing-trekbrain-geometry"
assert created["points_original"] == 5
assert db.committed == 1 and db.closed == 1
sql, parameters = db.statements[-1]
assert "INSERT INTO treks" in sql
assert "FALSE" in sql, "AI route must be private on initial save"
assert parameters["owner"] == 11
assert parameters["distance"] == ready["distance"]
assert json.loads(parameters["geo"])["type"] == "LineString"

db.statements.clear()
updated = update(739, plan, user={"id": 11, "is_admin": False})
assert updated["id"] == 739
assert updated["route_source"] == "existing-trekbrain-geometry"
assert db.committed == 2
assert len(db.statements) == 2
assert db.statements[-1][1]["id"] == 739
assert "UPDATE treks" in db.statements[-1][0]
assert "is_public" not in db.statements[-1][0], "update must preserve public/private state"

db.owner_id = 22
before_commit = db.committed
expect_http(403, lambda: update(739, plan, user={"id": 11, "is_admin": False}))
assert db.committed == before_commit
assert db.rolled_back == 1
db.exists = False
expect_http(404, lambda: update(739, plan, user={"id": 11, "is_admin": False}))
db.exists = True
db.owner_id = 22
admin_updated = update(739, plan, user={"id": 1, "is_admin": True})
assert admin_updated["id"] == 739

expect_http(422, lambda: _prepared_geometry(
    plan.model_copy(update={"coords": [[45.0, 5.0], [45.0, 5.0]]}), FakeLegacy))
expect_http(422, lambda: _prepared_geometry(
    plan.model_copy(update={"coords": [[45.0, 5.0], [91.0, 5.1]]}), FakeLegacy))
expect_http(422, lambda: _prepared_geometry(
    plan.model_copy(update={"coords": [[45.0, 5.0], [math.nan, 5.1]]}), FakeLegacy))
expect_http(422, lambda: _prepared_geometry(
    plan.model_copy(update={"coords": [[45.0, 5.0], [45.0, math.inf]]}), FakeLegacy))
for invalid in (
    {"coords": [[45.0, 5.0]]},
    {"coords": [[45.0, 5.0], [45.1, 5.1]] * (MAX_AI_ROUTE_POINTS // 2 + 1)},
    {"duration_days": 999},
    {"elevation_m": -2},
):
    try:
        TrekBrainGeometryPayload.model_validate({**plan.model_dump(), **invalid})
    except ValidationError:
        pass
    else:
        raise AssertionError("Unbounded input accepted: " + str(list(invalid)))

print("TrekBrain geometry persistence: authenticated private insert, owner-checked update, no ORS, route fidelity and bounds PASS")
