"""Regression tests for TrekBrain's matrix-first constraint planner."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_matrix_v9 as matrix_planner


stays = [
    {"name": "Camping nord", "lat": 48.72, "lon": -1.61, "source_url": "c1"},
    {"name": "Camping est", "lat": 48.63, "lon": -1.43, "source_url": "c2"},
    {"name": "Camping sud", "lat": 48.48, "lon": -1.55, "source_url": "c3"},
    {"name": "Camping mauvais", "lat": 48.55, "lon": -1.30, "source_url": "c4"},
]
for stay in stays:
    stay["_start_lat"] = 48.64
    stay["_start_lon"] = -1.51

intent = {
    "days": 4,
    "daily_target": 20.0,
    "daily_min": 17.0,
    "daily_max": 23.0,
    "total_target": 80.0,
}

matrix = [
    [0, 19, 31, 28, 29],
    [19, 0, 20, 30, 27],
    [31, 20, 0, 21, 29],
    [20, 30, 21, 0, 26],
    [29, 27, 29, 26, 0],
]
solutions = matrix_planner._matrix_sequences(matrix, stays, intent)
assert solutions, "Matrix planner should find the real 19/20/21/20 km loop"
best = solutions[0]
assert best[1] == [1, 2, 3], best
assert max(best[2]) <= 23.35, best
assert abs(sum(best[2]) - 80) <= 1.0, best
print("Matrix feasible loop: OK")

good3 = [
    [0, 19, 31, 28],
    [19, 0, 20, 30],
    [31, 20, 0, 21],
    [20, 30, 21, 0],
]

bad = [row[:] for row in good3]
bad[3][0] = 30
assert not matrix_planner._matrix_sequences(bad, stays[:3], intent), "30 km stage must be rejected"
print("Matrix daily maximum: OK")

unreachable = [row[:] for row in good3]
unreachable[1][2] = None
assert not matrix_planner._matrix_sequences(unreachable, stays[:3], intent), "Unroutable edge must not become a straight line"
print("Matrix unroutable edge: OK")

start = {"lat": 48.64, "lon": -1.51}
shape_ok = matrix_planner._shape_ratio(start, stays[:3])
line_stays = [
    {"lat": 48.65, "lon": -1.51},
    {"lat": 48.66, "lon": -1.51},
    {"lat": 48.67, "lon": -1.51},
]
shape_bad = matrix_planner._shape_ratio(start, line_stays)
assert shape_ok > shape_bad, (shape_ok, shape_bad)
assert shape_bad < 0.0015, shape_bad
print("Matrix anti out-and-back geometry: OK")
