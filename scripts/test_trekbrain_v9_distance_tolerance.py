"""Regression tests for TrekBrain v9 daily-distance tolerance."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import smart_planner_v3 as v3
from backend.free_planner_v2 import AIPlanRequest
from backend.trekbrain_distance_tolerance_v9 import install_distance_tolerance
from backend import trekbrain_matrix_v9 as matrix_planner

install_distance_tolerance(v3)


def req(prompt: str, daily_km: float = 20):
    return AIPlanRequest(
        prompt=prompt,
        region="Mont-Saint-Michel",
        days=4,
        daily_km=daily_km,
        difficulty="medium",
        route_type="Boucle",
        require_transit=False,
        require_water=False,
        require_accommodation=True,
        require_food=False,
    )


soft = v3._parse_intent(req(
    "Je veux une boucle de 4 jours au Mont Saint-Michel, environ 20 km par jour, avec des campings."
))
assert soft["daily_target"] == 20.0, soft
assert soft["daily_min"] == 15.0, soft
assert soft["daily_max"] == 25.0, soft
assert soft["distance_tolerance"] == "soft-25pct", soft
print("20 km target -> 15..25 km: OK")

explicit = v3._parse_intent(req(
    "Je veux une boucle de 4 jours avec entre 18 à 22 km par jour et des campings."
))
assert explicit["daily_min"] == 18.0, explicit
assert explicit["daily_max"] == 22.0, explicit
assert explicit["distance_tolerance"] == "explicit", explicit
print("Explicit 18..22 km range preserved: OK")

maximum = v3._parse_intent(req(
    "Je veux une boucle de 4 jours avec maximum 20 km par jour et des campings."
))
assert maximum["daily_max"] == 20.0, maximum
assert maximum["distance_tolerance"] == "explicit", maximum
print("Explicit daily maximum preserved: OK")

# The matrix solver must accept a useful 15/25/20/20 distribution when the
# user merely targets 20 km/day, while still rejecting a 26 km day.
stays = [
    {"name": "Camping 1", "lat": 48.70, "lon": -1.60, "source_url": "c1", "_start_lat": 48.64, "_start_lon": -1.51},
    {"name": "Camping 2", "lat": 48.72, "lon": -1.45, "source_url": "c2", "_start_lat": 48.64, "_start_lon": -1.51},
    {"name": "Camping 3", "lat": 48.57, "lon": -1.40, "source_url": "c3", "_start_lat": 48.64, "_start_lon": -1.51},
]
intent = dict(soft)
matrix = [
    [0, 15, 40, 40],
    [15, 0, 25, 40],
    [40, 25, 0, 20],
    [20, 40, 20, 0],
]
solutions = matrix_planner._matrix_sequences(matrix, stays, intent)
assert solutions, "15/25/20/20 should be feasible for a 20 km/day target"
assert solutions[0][2] == [15.0, 25.0, 20.0, 20.0], solutions[0]

bad = [row[:] for row in matrix]
bad[1][2] = 26
bad[2][1] = 26
assert not matrix_planner._matrix_sequences(bad, stays, intent), "26 km must exceed the 25 km default ceiling"
print("Matrix soft tolerance: OK")
