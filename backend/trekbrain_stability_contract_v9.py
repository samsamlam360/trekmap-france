"""Cross-scenario stability contracts for TrekBrain v9.

This module is deliberately boring. It does not plan routes, call providers or
patch the planner. It describes the invariants that must survive future changes.
That separation is intentional: TrekBrain accumulated many specialised recovery
layers, so we need one stable place that says what a valid result still means.

The contracts are used by CI as a release gate. They cover five reference cases:
- Belle-Île GR 340 without lodging constraints;
- Belle-Île GR 340 with camping logistics;
- Mont-Saint-Michel loop;
- a generic loop without a GR;
- a generic point-to-point traverse without a GR.

A result may use any internal strategy as long as it respects the corresponding
contract. This lets us simplify implementation later without rewriting the test
expectations around whichever wrapper happens to be fashionable this week.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StabilityCase:
    case_id: str
    route_type: str
    days: int
    daily_target: float
    daily_min: float
    daily_max: float
    region_contains: tuple[str, ...] = ()
    must_close: bool = False
    must_not_close: bool = False
    require_gr340: bool = False
    require_route_first_logistics: bool = False
    island_bounds: tuple[float, float, float, float] | None = None


# These are the five prompts manually validated by the product owner. They are
# intentionally stored verbatim so future parser or UI changes cannot quietly
# change what the stable release is expected to understand.
REFERENCE_PROMPTS: dict[str, str] = {
    "belle-ile-basic": (
        "Je veux faire le tour de Belle-Île-en-Mer en boucle sur 5 jours, environ 18 km par jour. "
        "Je veux suivre au maximum les vrais sentiers de randonnée et le GR 340 quand il existe."
    ),
    "belle-ile-camping": (
        "Je veux faire le tour de Belle-Île-en-Mer en boucle sur 5 jours, environ 18 km par jour, "
        "avec un camping pour dormir chaque soir. Je veux suivre au maximum le GR 340. "
        "Les campings peuvent nécessiter de petits détours mais ils ne doivent pas déformer le parcours principal."
    ),
    "mont-saint-michel-loop": (
        "Je veux une boucle de 4 jours autour du Mont-Saint-Michel, environ 18 km par jour, "
        "en privilégiant les vrais chemins de randonnée et les beaux paysages. "
        "Je veux des étapes cohérentes et éviter les passages non praticables à pied."
    ),
    "generic-loop-no-gr": (
        "Je veux une boucle de randonnée de 4 jours autour de Chartres, environ 20 km par jour. "
        "Il n'est pas obligatoire de suivre un GR : construis le meilleur itinéraire possible "
        "avec les vrais chemins pédestres et des étapes équilibrées."
    ),
    "generic-traverse-no-gr": (
        "Je veux faire un trek de Tours à Chinon en 3 jours, environ 25 km par jour. Ce n'est pas une boucle. "
        "Je veux suivre au maximum les vrais chemins de randonnée et les GR quand ils sont intéressants, "
        "avec des étapes cohérentes jusqu'à Chinon."
    ),
}


REFERENCE_CASES: dict[str, StabilityCase] = {
    "belle-ile-basic": StabilityCase(
        case_id="belle-ile-basic",
        route_type="Boucle",
        days=5,
        daily_target=18.0,
        daily_min=12.0,
        daily_max=25.0,
        region_contains=("belle", "ile"),
        must_close=True,
        require_gr340=True,
        island_bounds=(47.25, 47.42, -3.30, -3.02),
    ),
    "belle-ile-camping": StabilityCase(
        case_id="belle-ile-camping",
        route_type="Boucle",
        days=5,
        daily_target=18.0,
        daily_min=12.0,
        daily_max=25.0,
        region_contains=("belle", "ile"),
        must_close=True,
        require_gr340=True,
        require_route_first_logistics=True,
        island_bounds=(47.25, 47.42, -3.30, -3.02),
    ),
    "mont-saint-michel-loop": StabilityCase(
        case_id="mont-saint-michel-loop",
        route_type="Boucle",
        days=4,
        daily_target=18.0,
        # A deliberately short first day can be sensible around the bay. The
        # target is a preference, not a command to invent mileage.
        daily_min=8.0,
        daily_max=25.0,
        region_contains=("mont", "saint", "michel"),
        must_close=True,
    ),
    "generic-loop-no-gr": StabilityCase(
        case_id="generic-loop-no-gr",
        route_type="Boucle",
        days=4,
        daily_target=20.0,
        daily_min=15.0,
        daily_max=25.0,
        must_close=True,
    ),
    "generic-traverse-no-gr": StabilityCase(
        case_id="generic-traverse-no-gr",
        route_type="Traversée",
        days=3,
        daily_target=25.0,
        daily_min=18.0,
        daily_max=30.0,
        must_not_close=True,
    ),
}


def _fold(value: Any) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def _distance_km(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    if not a or not b:
        return None
    try:
        lat1, lon1 = math.radians(float(a["lat"])), math.radians(float(a["lon"]))
        lat2, lon2 = math.radians(float(b["lat"])), math.radians(float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def _valid_coords(result: dict[str, Any]) -> list[list[float]]:
    route = result.get("route_preview") or {}
    rows = []
    for point in route.get("coords") or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lat, lon = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            rows.append([lat, lon])
    return rows


def validate_result(case_id: str, result: dict[str, Any]) -> list[str]:
    """Return human-readable contract violations for one reference scenario."""
    case = REFERENCE_CASES[case_id]
    issues: list[str] = []

    route = result.get("route_preview") or {}
    coords = _valid_coords(result)
    if len(coords) < 2:
        issues.append("route geometry is missing or invalid")
    if route.get("fallback") is not False:
        issues.append("reference route must be a validated pedestrian geometry, not a direct fallback")

    route_type = _fold(result.get("route_type") or "")
    if _fold(case.route_type) not in route_type:
        issues.append(f"route type must stay {case.route_type}")

    stages = [x for x in (result.get("stages") or []) if isinstance(x, dict)]
    if len(stages) != case.days:
        issues.append(f"expected {case.days} stages, got {len(stages)}")
    distances = []
    for index, stage in enumerate(stages, 1):
        try:
            distance = float(stage.get("distance_km") or 0)
        except (TypeError, ValueError):
            distance = 0.0
        if not math.isfinite(distance) or distance <= 0:
            issues.append(f"day {index} has no usable distance")
            continue
        distances.append(distance)
        if distance < case.daily_min - 0.1 or distance > case.daily_max + 0.1:
            issues.append(
                f"day {index} distance {distance:.1f} km outside stable range "
                f"{case.daily_min:.1f}-{case.daily_max:.1f} km"
            )

    if case.region_contains:
        region_text = _fold(" ".join(str(result.get(k) or "") for k in ("region", "name", "description")))
        if not all(token in region_text for token in case.region_contains):
            issues.append("result no longer identifies the requested geographic area")

    closing = _distance_km(result.get("start"), result.get("end"))
    if case.must_close and (closing is None or closing > 0.75):
        issues.append(f"loop no longer closes (gap={closing!r} km)")
    if case.must_not_close and closing is not None and closing < 2.0:
        issues.append("point-to-point traverse collapsed into a loop")

    if case.require_gr340:
        text = _fold(
            " ".join(
                str(x or "")
                for x in (
                    route.get("relation_ref"), route.get("relation_name"),
                    result.get("planner_fallback"), result.get("name"), result.get("description"),
                )
            )
        )
        if "gr 340" not in text:
            issues.append("Belle-Île reference route must retain GR 340 as its walking backbone")

    if case.island_bounds and coords:
        south, north, west, east = case.island_bounds
        outside = [p for p in coords if not (south <= p[0] <= north and west <= p[1] <= east)]
        if outside:
            issues.append("Belle-Île walking geometry escaped the island bounds")

    if case.require_route_first_logistics:
        logistics = result.get("logistics") or {}
        if logistics.get("mode") != "route-first":
            issues.append("lodging must stay in route-first logistics mode")
        if logistics.get("route_immutable") is not True:
            issues.append("lodging must not reshape the hiking backbone")
        required = max(0, case.days - 1)
        try:
            nights_required = int(logistics.get("nights_required", -1))
        except (TypeError, ValueError):
            nights_required = -1
        if nights_required != required:
            issues.append(f"expected logistics for {required} nights")

    for water in result.get("water") or []:
        if isinstance(water, dict) and water.get("display_only") is not True:
            issues.append("water markers must remain display-only and must not shape the route")
            break

    return issues


def assert_reference(case_id: str, result: dict[str, Any]) -> None:
    issues = validate_result(case_id, result)
    if issues:
        raise AssertionError(f"{case_id}: " + " | ".join(issues))


__all__ = [
    "StabilityCase",
    "REFERENCE_PROMPTS",
    "REFERENCE_CASES",
    "validate_result",
    "assert_reference",
]
