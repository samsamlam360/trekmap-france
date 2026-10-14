"""Production end-to-end benchmark for TrekBrain v9.

This script talks to the public Render service exactly like a browser client:
it creates a disposable authenticated account, runs realistic hiking requests,
measures the returned plans, writes JSON/Markdown reports, and deletes the
account again even when a scenario fails.

No repository or Render secret is required.
"""
from __future__ import annotations

import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import secrets
import statistics
import time
import urllib.error
import urllib.request

BASE_URL = os.getenv("TREKBRAIN_BENCHMARK_URL", "https://trekmap-france.onrender.com").rstrip("/")
OUT_DIR = Path(os.getenv("TREKBRAIN_BENCHMARK_OUT", "benchmark-results"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
EXPECTED_SHA = os.getenv("EXPECTED_SHA", "").strip().lower()
RUN_ID = os.getenv("GITHUB_RUN_ID", str(int(time.time()))).strip()

SCENARIOS = [
    {
        "id": "belle-ile-gr340-camping",
        "prompt": (
            "Je veux faire le tour de Belle-Île-en-Mer en boucle sur 5 jours, environ 18 km par jour. "
            "Je veux suivre au maximum le GR 340, dormir en camping chaque soir, avoir des points d'eau "
            "et du ravitaillement, avec une solution de transport pour rejoindre l'île."
        ),
        "region": "Bretagne", "days": 5, "daily_km": 18, "difficulty": "medium",
        "route_type": "Traversée", "require_transit": True, "require_water": True,
        "require_accommodation": True, "require_food": True,
        "expect_type": "boucle", "expect_close": True, "expect_gr340": True,
        "island_bounds": [47.24, 47.43, -3.31, -3.00],
    },
    {
        "id": "tours-chinon-traverse",
        "prompt": (
            "Je veux aller de Tours à Chinon à pied en 3 jours, environ 22 km par jour. Ce n'est pas une boucle. "
            "Je veux de vrais chemins de randonnée, des points d'eau, du ravitaillement et des gares ou transports "
            "utiles au départ et à l'arrivée."
        ),
        "region": "Chartres", "days": 3, "daily_km": 22, "difficulty": "medium",
        "route_type": "Boucle", "require_transit": True, "require_water": True,
        "require_accommodation": True, "require_food": True,
        "expect_type": "traversee", "expect_close": False,
    },
    {
        "id": "vercors-refuges",
        "prompt": (
            "Je veux une boucle sportive de 3 jours dans le Vercors, autour de 15 km par jour, avec des refuges "
            "ou gîtes pour dormir et des points d'eau. Privilégie les vrais sentiers et évite les journées irréalistes."
        ),
        "region": "Vercors", "days": 3, "daily_km": 15, "difficulty": "hard",
        "route_type": "Boucle", "require_transit": False, "require_water": True,
        "require_accommodation": True, "require_food": False,
        "expect_type": "boucle", "expect_close": True,
    },
    {
        "id": "mont-saint-michel-safe-loop",
        "prompt": (
            "Je veux une boucle de randonnée de 2 jours autour du Mont-Saint-Michel, environ 16 km par jour. "
            "Je ne veux pas traverser la baie à pied : reste sur des chemins terrestres praticables. "
            "Je veux de l'eau, du ravitaillement et un hébergement."
        ),
        "region": "Normandie", "days": 2, "daily_km": 16, "difficulty": "easy",
        "route_type": "Boucle", "require_transit": True, "require_water": True,
        "require_accommodation": True, "require_food": True,
        "expect_type": "boucle", "expect_close": True,
    },
    {
        "id": "sancy-loop",
        "prompt": (
            "Je veux une boucle de 3 jours dans le massif du Sancy, environ 17 km par jour, avec de beaux paysages, "
            "des points d'eau, une solution pour dormir chaque soir et du ravitaillement quand c'est possible."
        ),
        "region": "Massif du Sancy", "days": 3, "daily_km": 17, "difficulty": "medium",
        "route_type": "Boucle", "require_transit": False, "require_water": True,
        "require_accommodation": True, "require_food": True,
        "expect_type": "boucle", "expect_close": True,
    },
    {
        "id": "morvan-settons-camping",
        "prompt": (
            "Je veux une boucle tranquille de 3 jours dans le Morvan autour du lac des Settons, environ 16 km par jour, "
            "avec camping, eau et ravitaillement. Utilise de vrais chemins pédestres et garde des étapes équilibrées."
        ),
        "region": "Lac des Settons, Morvan", "days": 3, "daily_km": 16, "difficulty": "easy",
        "route_type": "Boucle", "require_transit": False, "require_water": True,
        "require_accommodation": True, "require_food": True,
        "expect_type": "boucle", "expect_close": True,
    },
]


def fold(value):
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def haversine(a, b):
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


def valid_coords(result):
    out = []
    for p in ((result.get("route_preview") or {}).get("coords") or []):
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        try:
            lat, lon = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append([lat, lon])
    return out


def _resource_days(points, kind, days):
    """Count route-local evidence, never generic stage advice or map counts."""
    found = set()
    for row in points:
        if not isinstance(row, dict) or row.get("kind") != kind:
            continue
        if not re.fullmatch(r"https://(?:www\.)?openstreetmap\.org/(?:node|way|relation)/[1-9]\d*", str(row.get("source_url") or "")):
            continue
        if kind == "water" and row.get("status") != "potable_referenced":
            continue
        if isinstance(row.get("route_day"), bool):
            continue
        try:
            day = int(row.get("route_day"))
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if 1 <= day <= days and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            found.add(day)
    return found


def preparation_issues(case, result, distance_excess):
    """Verify required needs independently of a reassuring quality score."""
    days = int(case["days"])
    issues = []

    def add(code, requirement, missing, detail):
        issues.append({"code": code, "requirement": requirement, "days": missing, "detail": detail})

    readiness = result.get("trip_readiness") or {}
    if readiness.get("version") == 1:
        issues.extend(row for row in readiness.get("issues") or [] if isinstance(row, dict))
        requirements = readiness.get("requirements") or {}
        effective = result.get("effective_request") or {}
        mandatory = ["route", "distance"] + [name for name, flag in (
            ("water", "require_water"), ("food", "require_food"),
            ("accommodation", "require_accommodation"), ("transit", "require_transit"),
        ) if effective.get(flag, case.get(flag)) and (name != "accommodation" or days > 1)]
        for name in mandatory:
            requirement = requirements.get(name)
            if not isinstance(requirement, dict) or requirement.get("required") is not True:
                add("requirement_telemetry_missing", name, [], f"Besoin obligatoire {name} absent du verdict")
        for name, requirement in requirements.items():
            if isinstance(requirement, dict) and requirement.get("required") is True and requirement.get("status") != "confirmed":
                add("requirement_unconfirmed", name, requirement.get("missing_days") or [], str(requirement.get("detail") or f"{name}: non confirmé"))
        if readiness.get("status") != "ready" and not issues:
            add("readiness_incomplete", "readiness", [], str(readiness.get("label") or readiness.get("status") or "Verdict absent"))
        if distance_excess:
            add("distance_exceeded", "distance", [row["day"] for row in distance_excess], "Distance au-dessus de la demande")
        for blocker in ((result.get("trekbrain") or {}).get("quality") or {}).get("blockers") or []:
            add("quality_blocker", "quality", [], str(blocker))
        return issues

    resources = result.get("map_resources") or {}
    points = resources.get("evidence_points") if isinstance(resources.get("evidence_points"), list) else resources.get("points") or []
    for flag, kind, detail in (
        ("require_water", "water", "Eau potable référencée manquante"),
        ("require_food", "food", "Ravitaillement sourcé manquant"),
    ):
        if case.get(flag):
            covered = _resource_days(points, kind, days)
            missing = [day for day in range(1, days + 1) if day not in covered]
            if missing:
                add(f"{kind}_missing", kind, missing, detail)

    if case.get("require_accommodation"):
        nights = [row for row in ((result.get("logistics") or {}).get("nights") or []) if isinstance(row, dict)]
        confirmed = {
            row.get("night") for row in nights
            if row.get("status") == "confirmed" and row.get("access_mode") == "walk"
        }
        confirmed.update(
            row.get("night") for row in nights
            if row.get("status") == "usable_with_transfer" and row.get("transfer_confirmed") is True
        )
        missing = [night for night in range(1, days) if night not in confirmed]
        if missing:
            add("accommodation_missing", "accommodation", missing, "Nuitée ou transfert restant à confirmer")

    if case.get("require_transit"):
        transport = result.get("transport") or {}
        for field, endpoint in (("outbound_point", "start"), ("return_point", "end")):
            point = transport.get(field) or {}
            gap = haversine(point, result.get(endpoint))
            if not str(point.get("source_url") or "").startswith("https://") or gap is None or not math.isfinite(gap) or gap > 8.0:
                add("transit_unverified", "transit", [], f"Accès transport {endpoint} sans point sourcé proche")

    if distance_excess:
        add("distance_exceeded", "distance", [row["day"] for row in distance_excess], "Distance au-dessus de la demande")

    quality = ((result.get("trekbrain") or {}).get("quality") or {})
    for blocker in quality.get("blockers") or []:
        add("quality_blocker", "quality", [], str(blocker))

    if readiness.get("status") in {"incomplete", "refused"}:
        for issue in readiness.get("issues") or []:
            if isinstance(issue, dict) and issue not in issues:
                issues.append(issue)
        if not readiness.get("issues"):
            add("readiness_incomplete", "readiness", [], str(readiness.get("label") or readiness["status"]))
    return issues


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self):
        for cookie in self.jar:
            if cookie.name == "trekmap_csrf":
                return cookie.value
        return ""

    def json(self, method, path, payload=None, timeout=45):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "TrekBrain-production-benchmark/1.0"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if method not in {"GET", "HEAD"} and self.csrf():
            headers["X-CSRF-Token"] = self.csrf()
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        started = time.perf_counter()
        try:
            with self.opener.open(req, timeout=timeout) as response:
                raw = response.read()
                value = json.loads(raw.decode("utf-8")) if raw else {}
                return response.status, value, round(time.perf_counter() - started, 3)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                value = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                value = {"detail": raw.decode("utf-8", "replace")[:1000]}
            return exc.code, value, round(time.perf_counter() - started, 3)


def evaluate(case, result, elapsed_s, clarify):
    hard, warnings = [], []
    route = result.get("route_preview") or {}
    coords = valid_coords(result)
    stages = [x for x in (result.get("stages") or []) if isinstance(x, dict)]
    quality_obj = ((result.get("trekbrain") or {}).get("quality") or {})
    quality = quality_obj.get("score")
    decision = result.get("decision_summary") or {}
    performance = ((result.get("agent") or {}).get("performance") or {})
    perf_ms = performance.get("total_ms")
    closing = haversine(result.get("start"), result.get("end"))

    if len(coords) < 2:
        hard.append("géométrie absente ou invalide")
    elif len(coords) != len(route.get("coords") or []):
        hard.append("géométrie contenant des coordonnées invalides")
    if route.get("fallback") is not False:
        hard.append("routage pédestre en fallback")
    if len(stages) != int(case["days"]):
        hard.append(f"{len(stages)} étapes au lieu de {case['days']}")

    route_type = fold(result.get("route_type"))
    if case["expect_type"] not in route_type:
        hard.append(f"type d'itinéraire inattendu: {result.get('route_type')!r}")

    if case.get("expect_close") is True and (closing is None or closing > 1.5):
        hard.append(f"boucle mal refermée: {closing!r} km")
    if case.get("expect_close") is False and closing is not None and closing < 2.0:
        hard.append(f"traversée rabattue en boucle: {closing:.2f} km")

    distances = []
    for stage in stages:
        try:
            d = float(stage.get("distance_km") or 0)
        except (TypeError, ValueError):
            d = 0
        if math.isfinite(d) and d > 0 and not isinstance(stage.get("distance_km"), bool):
            distances.append(d)
    target = float(case["daily_km"])
    mean_dev = statistics.fmean(abs(x - target) / target for x in distances) if distances else 1.0
    worst_dev = max((abs(x - target) / target for x in distances), default=1.0)
    if len(distances) != len(stages) or not distances:
        hard.append("distances d'étape manquantes ou invalides")
    elif mean_dev > 0.35:
        warnings.append(f"écart moyen aux km/jour élevé: {mean_dev*100:.0f}%")
    if worst_dev > 0.55:
        warnings.append(f"une journée s'écarte fortement de la cible: {worst_dev*100:.0f}%")

    # The user sees a distance warning from +18% AND +2 km; the historical
    # benchmark only warned at +35% average / +55% worst. That hid real
    # 20%-oversized hikes under the reassuring but misleading label "aucune".
    distance_excess = []
    for index, stage in enumerate(stages):
        if isinstance(stage.get("distance_km"), bool):
            continue
        try:
            km = float(stage.get("distance_km") or 0)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(km):
            continue
        if km > target * 1.18 and km - target >= 2.0:
            distance_excess.append({
                "day": index + 1,
                "km": round(km, 1),
                "extra_pct": round((km / target - 1) * 100),
            })
    contract = ((result.get("planner") or {}).get("distance_contract") or {})
    reported_days = {
        int(x.get("day")) for x in (contract.get("days_exceeding") or [])
        if isinstance(x, dict) and isinstance(x.get("day"), int)
    }
    unreported_distance_days = [x["day"] for x in distance_excess if x["day"] not in reported_days]
    if distance_excess:
        warnings.append(
            "distance au-dessus de la demande : "
            + ", ".join(f"J{x['day']} {x['km']:.1f} km (+{x['extra_pct']}%)" for x in distance_excess)
        )
    if unreported_distance_days:
        warnings.append(
            "alerte de distance absente du contrat de réponse pour les jours "
            + ", ".join(str(day) for day in unreported_distance_days)
        )

    if coords:
        mainland_ok = all(41.0 <= p[0] <= 51.6 and -5.6 <= p[1] <= 10.0 for p in coords)
        if not mainland_ok:
            hard.append("coordonnées hors enveloppe France métropolitaine attendue")

    bounds = case.get("island_bounds")
    if bounds and coords:
        south, north, west, east = bounds
        if any(not (south <= lat <= north and west <= lon <= east) for lat, lon in coords):
            hard.append("géométrie Belle-Île sortie de l'île")

    if case.get("expect_gr340"):
        gr_text = fold(" ".join(str(x or "") for x in (
            route.get("relation_ref"), route.get("relation_name"),
            result.get("name"), result.get("description"), result.get("planner_fallback"),
        )))
        if "gr 340" not in gr_text:
            hard.append("GR 340 non identifié comme backbone")

    if case.get("require_water"):
        water = result.get("water") or []
        stage_water = [str(x.get("water_notes") or "") for x in stages]
        if not water and not any(x.strip() for x in stage_water):
            warnings.append("aucune information eau retournée")

    if case.get("require_accommodation") and int(case["days"]) > 1:
        overnight = [str(x.get("overnight") or "").strip() for x in stages[:-1]]
        if not overnight or all(not x for x in overnight):
            warnings.append("nuitées non renseignées")

    food_markers = sum(
        1 for item in ((result.get("map_resources") or {}).get("evidence_points") or (result.get("map_resources") or {}).get("points") or [])
        if isinstance(item, dict) and item.get("kind") == "food"
        and item.get("source_url") and item.get("lat") is not None and item.get("lon") is not None
    )
    cache_context = ((result.get("planner") or {}).get("resource_overlay") or {}).get("osm_cache") or {}
    cold_cache = cache_context.get("status") == "miss" and int(cache_context.get("count") or 0) == 0
    food_coverage = ((result.get("map_resources") or {}).get("coverage") or {}).get("food")
    missing_food_days = ((result.get("map_resources") or {}).get("coverage") or {}).get("days_without_food") or []
    missing_water_days = ((result.get("map_resources") or {}).get("coverage") or {}).get("days_without_water") or []

    # Overnight candidates are not automatically usable overnight stops.
    # Keep walk-validated nights separate from transfer-only accommodation,
    # instead of inflating the campsite count with merely mapped POIs.
    logistics = result.get("logistics") or {}
    nights = [
        row for row in logistics.get("nights") or []
        if isinstance(row, dict)
    ]
    walk_nights = sum(
        row.get("status") == "confirmed" and row.get("access_mode") == "walk"
        for row in nights
    )
    transfer_nights = sum(
        row.get("status") == "usable_with_transfer"
        for row in nights
    )
    required_nights = max(0, int(case["days"]) - 1)
    unresolved_nights = max(0, required_nights - walk_nights - transfer_nights)
    source_water = [
        row for row in ((result.get("map_resources") or {}).get("evidence_points") or (result.get("map_resources") or {}).get("points") or [])
        if isinstance(row, dict) and row.get("kind") == "water"
        and str(row.get("source_url") or "").startswith(
            "https://www.openstreetmap.org/"
        )
    ]
    referenced_potable = sum(
        row.get("status") == "potable_referenced" for row in source_water
    )
    explicitly_nonpotable = sum(
        row.get("status") == "not_potable" for row in source_water
    )
    if case.get("require_water") and missing_water_days:
        warnings.append(
            "eau non vérifiée sur les jours "
            + ", ".join(str(x) for x in missing_water_days)
        )
    cache_metrics = ((result.get("planner") or {}).get("resource_overlay") or {}).get("osm_cache") or {}
    if case.get("require_food") and food_markers and missing_food_days:
        warnings.append(
            "ravitaillement partiel : aucun commerce OSM confirmé pour les jours "
            + ", ".join(str(x) for x in missing_food_days)
        )
    if case.get("require_food") and food_markers == 0:
        warnings.append(
            "recherche des commerces indisponible chez les fournisseurs"
            if food_coverage == "providers_unavailable"
            else "aucun commerce OSM confirmé à proximité du tracé"
        )

    if case.get("require_transit"):
        transport = result.get("transport") or {}
        if not str(transport.get("outbound") or "").strip() or not str(transport.get("return") or "").strip():
            warnings.append("transport aller/retour incomplet")

    quality_blockers = ((result.get("trekbrain") or {}).get("quality") or {}).get("blockers") or []
    critical_quality_blockers = {
        "durée différente de la demande",
        "distances manquantes ou invalides",
        "distance maximale dépassée",
        "routage dégradé",
        "boucle mal refermée",
        "fermeture de boucle invérifiable",
    }
    for blocker in quality_blockers:
        if str(blocker) in critical_quality_blockers:
            hard.append(f"audit TrekBrain: {blocker}")

    if quality is None:
        warnings.append("score TrekBrain absent")
    else:
        try:
            q = float(quality)
            if isinstance(quality, bool) or not math.isfinite(q):
                raise ValueError("invalid quality score")
            quality = q
            # This score is explicitly heuristic, not a success probability.
            # Structural invariants above are the hard gate.
            if q < 40:
                hard.append(f"score TrekBrain extrêmement faible: {q:.1f}/100")
            elif q < 60:
                warnings.append(f"score TrekBrain faible: {q:.1f}/100")
            elif q < 76:
                warnings.append(f"score TrekBrain à vérifier: {q:.1f}/100")
        except (TypeError, ValueError):
            warnings.append("score TrekBrain illisible")
            quality = None

    if elapsed_s > 90:
        warnings.append(f"latence élevée: {elapsed_s:.1f}s")

    issues = preparation_issues(case, result, distance_excess)
    if quality is not None and quality < 60 and not any(issue.get("code") == "audit_fragile" for issue in issues):
        issues.append({"code": "audit_fragile", "requirement": "audit", "days": [], "detail": f"Audit fragile ({quality:.1f}/100)"})
    structure_ok = not hard
    preparation_ok = not issues
    published = result.get("trip_readiness") or {}
    category = "refused" if not structure_ok or published.get("status") == "refused" else "ready" if preparation_ok else "incomplete"
    if published.get("status") == "ready" and not (structure_ok and preparation_ok):
        warnings.append("verdict prêt à partir contredit par les preuves du benchmark")

    return {
        "id": case["id"],
        "ok": structure_ok and preparation_ok,
        "structure_ok": structure_ok,
        "preparation_ok": preparation_ok,
        "status": category,
        "preparation_issues": issues,
        "trip_readiness": published,
        "geocoding": ((result.get("request_resolution") or {}).get("geocoding") or {}),
        "hard_failures": hard,
        "warnings": warnings,
        "elapsed_s": elapsed_s,
        "planner_ms": perf_ms,
        "quality": quality,
        "grade": ((result.get("trekbrain") or {}).get("quality") or {}).get("grade"),
        "decision_grade": decision.get("grade"),
        "route_type": result.get("route_type"),
        "routing_mode": route.get("routing_mode"),
        "planner_fallback": result.get("planner_fallback"),
        "fast_roundtrip": (result.get("planner") or {}).get("fast_roundtrip"),
        "route_distance_km": route.get("distance_km"),
        "stage_distances_km": distances,
        "mean_daily_deviation_pct": round(mean_dev * 100, 1),
        "worst_daily_deviation_pct": round(worst_dev * 100, 1),
        "distance_days_above_target": distance_excess,
        "distance_days_missing_warning": unreported_distance_days,
        "closing_gap_km": round(closing, 3) if closing is not None else None,
        "coords": len(coords),
        "water_markers": len(result.get("water") or []),
        "food_markers": food_markers,
        "food_coverage": food_coverage,
        "food_days_missing": missing_food_days,
        "water_days_missing": missing_water_days,
        "osm_cache_hits": int(cache_metrics.get("count") or 0),
        "cold_cache": cold_cache,
        "osm_cache_status": cache_metrics.get("status"),
        "accommodations": len(result.get("accommodations") or []),
        "nights_required": required_nights,
        "nights_walk_confirmed": walk_nights,
        "nights_transfer_only": transfer_nights,
        "nights_unresolved": unresolved_nights,
        "lodging_category": logistics.get("category"),
        "water_potable_referenced": referenced_potable,
        "water_explicitly_nonpotable": explicitly_nonpotable,
        "web_sources": len(result.get("web_sources") or []),
        "clarification_needed": bool((clarify or {}).get("needs_clarification")),
        "clarification_questions": (clarify or {}).get("questions") or [],
        "strategy": (result.get("trekbrain") or {}).get("strategy"),
        "blockers": quality_obj.get("blockers") or [],
        "quality_checks": quality_obj.get("checks") or [],
        "quality_reasons": quality_obj.get("reasons") or [],
        "base_local_score": quality_obj.get("base_local_score"),
        "confidence_score": (result.get("confidence") or {}).get("score"),
        "confidence_limitations": (result.get("confidence") or {}).get("limitations") or [],
        "performance": performance,
        "planner_diagnostics": {
            key: (result.get("planner") or {}).get(key)
            for key in (
                "pipeline_version", "pipeline_phases", "strategy",
                "candidates_compared", "corridor_centered", "search_center",
                "stage_rebalanced", "logistics_mode", "resource_overlay",
            )
            if key in (result.get("planner") or {})
        },
        "logistics_diagnostics": {
            "status": (result.get("logistics") or {}).get("status"),
            "discovered_candidates": (result.get("logistics") or {}).get("discovered_candidates"),
            "nights_resolved": (result.get("logistics") or {}).get("nights_resolved"),
            "night_diagnostics": (result.get("logistics") or {}).get("night_diagnostics") or [],
            "timing": (result.get("logistics") or {}).get("timing") or {},
        },
    }


def write_reports(meta, rows):
    payload = {"meta": meta, "scenarios": rows}
    (OUT_DIR / "trekbrain-production-benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    elapsed = [float(x["elapsed_s"]) for x in rows]
    qualities = [float(x["quality"]) for x in rows if isinstance(x.get("quality"), (int, float))]
    ok = sum(1 for x in rows if x["ok"])
    structural = sum(1 for x in rows if x.get("structure_ok"))
    warnings = sum(len(x["warnings"]) for x in rows)
    # Cold-cache means a confirmed zero-hit DB lookup, not a cache provider
    # outage or a failed HTTP request with no telemetry.
    cold_rows = [x for x in rows if x.get("cold_cache") is True]
    cold_food = [x for x in cold_rows if x.get("food_coverage") != "not_requested"]
    lines = [
        f"# TrekBrain v9 — benchmark {meta.get('suite') or 'production'}",
        "",
        f"- Build: `{str(meta.get('build_commit') or 'non renseigné')[:12]}`",
        f"- Scénarios structurellement valides: **{structural}/{len(rows)}**",
        f"- Scénarios avec préparation complète: **{ok}/{len(rows)}**",
        f"- Routes réellement sans cache OSM: **{len(cold_rows)}/{len(rows)}**",
        f"- Ravitaillements sourcés sans cache OSM: **{sum(int(x.get('food_markers') or 0) for x in cold_food)}**",
        f"- Journées sans ravitaillement sur routes sans cache: **{sum(len(x.get('food_days_missing') or []) for x in cold_food)}**",
        f"- Qualité moyenne TrekBrain: **{statistics.fmean(qualities):.1f}/100**" if qualities else "- Qualité moyenne: n/a",
        f"- Latence moyenne: **{statistics.fmean(elapsed):.1f} s**" if elapsed else "- Latence moyenne: n/a",
        f"- Latence max: **{max(elapsed):.1f} s**" if elapsed else "- Latence max: n/a",
        f"- Nuitées accessibles à pied avec liaison validée: **{sum(int(x.get('nights_walk_confirmed') or 0) for x in rows)}**",
        f"- Nuitées nécessitant un transfert: **{sum(int(x.get('nights_transfer_only') or 0) for x in rows)}**",
        f"- Nuitées non résolues: **{sum(int(x.get('nights_unresolved') or 0) for x in rows)}**",
        "- Raisons des nuitées non préparées : "
        + (", ".join(
            f"{reason}={count}"
            for reason, count in sorted(__import__("collections").Counter(
                item.get("reason") for row in rows
                for item in (row.get("logistics_diagnostics") or {}).get("night_diagnostics", [])
                if item.get("reason") != "walk_verified"
            ).items())
        ) or "aucune donnée"),
        f"- Points d'eau avec potabilité référencée: **{sum(int(x.get('water_potable_referenced') or 0) for x in rows)}**",
        f"- Points d'eau explicitement non potables: **{sum(int(x.get('water_explicitly_nonpotable') or 0) for x in rows)}**",
        f"- Avertissements terrain: **{warnings}**",
        "",
        "| Scénario | Tracé | Préparation | Qualité | Temps | Commerces sourcés | Recherche | Moteur | Distance | Écart/jour | Alertes |",
        "|---|---:|---|---:|---:|---:|---|---|---:|---:|---|",
    ]
    if meta.get("error"):
        lines[4:4] = [f"- Erreur d'exécution: **{str(meta['error']).replace('|', '/')}**"]
    for row in rows:
        issues = [str(issue.get("detail") or issue.get("code")) for issue in row.get("preparation_issues") or [] if isinstance(issue, dict)]
        alerts = "; ".join(dict.fromkeys(row["hard_failures"] + issues + row["warnings"])) or "aucune"
        quality = "n/a" if row["quality"] is None else f"{float(row['quality']):.1f}"
        distance = row["route_distance_km"]
        distance = "n/a" if distance is None else f"{float(distance):.1f} km"
        routing = str(row.get("routing_mode") or row.get("planner_fallback") or "n/a")
        if row.get("fast_roundtrip"):
            routing += " · fast"
        lines.append(
            f"| {row['id']} | {'✅' if row.get('structure_ok') else '❌'} | {row.get('status', 'refused')} | {quality} | {row['elapsed_s']:.1f}s | "
            f"{row.get('food_markers', 0)} | {row.get('food_coverage') or 'inconnue'} | {routing.replace('|','/')} | {distance} | {row['mean_daily_deviation_pct']:.1f}% | "
            f"{alerts.replace('|','/')} |"
        )
    (OUT_DIR / "trekbrain-production-benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def failure_row(case_id, error, elapsed=0.0, *, status="refused", http_status=None):
    """Keep failures in the report even when no planner payload exists."""
    row = {
        "id": case_id, "ok": False, "structure_ok": False,
        "preparation_ok": False, "status": status,
        "hard_failures": [str(error)], "preparation_issues": [], "warnings": [],
        "elapsed_s": round(elapsed, 3), "error": str(error), "quality": None,
        "route_distance_km": None, "mean_daily_deviation_pct": 100.0,
        "worst_daily_deviation_pct": 100.0, "stage_distances_km": [],
        "cold_cache": None, "coords": 0,
    }
    if http_status is not None:
        row["http_status"] = http_status
    return row


def main():
    client = Client(BASE_URL)
    suffix = (EXPECTED_SHA[:8] or secrets.token_hex(4)) + "_" + RUN_ID[-8:]
    username = ("trekbench_" + suffix)[:70]
    email = f"{username}@example.invalid"
    password = "Tb!" + secrets.token_urlsafe(24)
    registered = False
    rows = []
    status_payload = {}
    suite_error = None

    try:
        # A successful deployment of /ai/status does not imply PostgreSQL is
        # ready for authentication. Never benchmark a dead database, and do
        # not count a transient 503 as an itinerary failure. Retry readiness
        # briefly, then report a distinct infrastructure failure.
        readiness_history = []
        for attempt, delay in enumerate((0, 5, 10, 15)):
            if delay:
                time.sleep(delay)
            try:
                rcode, readiness, _ = client.json("GET", "/health/ready", timeout=20)
            except Exception as exc:
                rcode, readiness = 0, {"error": type(exc).__name__}
            readiness_history.append({"status": rcode, "details": readiness})
            if rcode == 200 and isinstance(readiness, dict) and readiness.get("status") == "ok":
                break
        else:
            raise RuntimeError(
                "POSTGRES_UNAVAILABLE: readiness did not recover after bounded "
                f"retries: {readiness_history}"
            )

        code, reg, _ = client.json("POST", "/auth/register", {
            "username": username, "email": email, "password": password,
        })
        if code != 200:
            raise RuntimeError(f"registration HTTP {code}: {reg}")
        registered = True

        code, me, _ = client.json("GET", "/auth/me")
        if code != 200:
            raise RuntimeError(f"auth/me HTTP {code}: {me}")

        code, status_payload, _ = client.json("GET", "/ai/status")
        if code != 200:
            raise RuntimeError(f"ai/status HTTP {code}: {status_payload}")
        if EXPECTED_SHA and str(status_payload.get("build_commit") or "").lower() != EXPECTED_SHA:
            raise RuntimeError(
                f"production build mismatch: {status_payload.get('build_commit')} != {EXPECTED_SHA}"
            )

        last_started = None
        interval = max(0.0, min(60.0, float(os.getenv("TREKBRAIN_BENCHMARK_MIN_INTERVAL_SECONDS", "20"))))
        for case in SCENARIOS:
            if last_started is not None:
                time.sleep(max(0.0, interval - (time.monotonic() - last_started)))
            last_started = time.monotonic()
            payload = {k: v for k, v in case.items() if k in {
                "prompt", "region", "days", "daily_km", "difficulty", "route_type",
                "require_transit", "require_water", "require_accommodation", "require_food",
            }}
            clarify_started = time.perf_counter()
            try:
                ccode, clarify, clarify_s = client.json("POST", "/ai/clarify", payload, timeout=90)
                if ccode != 200 or not isinstance(clarify, dict):
                    clarify = {"needs_clarification": None, "error": clarify, "http": ccode}
            except Exception as exc:
                clarify_s = round(time.perf_counter() - clarify_started, 3)
                clarify = {"needs_clarification": None, "error": type(exc).__name__}

            plan_started = time.perf_counter()
            try:
                pcode, plan, plan_s = client.json("POST", "/ai/plan", payload, timeout=180)
            except Exception as exc:
                rows.append(failure_row(case["id"], type(exc).__name__, time.perf_counter() - plan_started))
                print(f"[{case['id']}] refused (request failed)", flush=True)
                continue
            if pcode != 200:
                detail = plan.get("detail", plan) if isinstance(plan, dict) else plan
                rows.append(failure_row(case["id"], f"/ai/plan HTTP {pcode}: {detail}", plan_s, http_status=pcode))
                continue

            try:
                if not isinstance(plan, dict):
                    raise TypeError("unexpected planner response")
                row = evaluate(case, plan, plan_s, clarify)
            except (TypeError, ValueError, KeyError, AttributeError) as exc:
                row = failure_row(case["id"], f"response_contract_error: {type(exc).__name__}", plan_s, status="runtime_error")
            row["clarify_elapsed_s"] = clarify_s
            rows.append(row)
            print(
                f"[{case['id']}] {row['status']} structure={row['structure_ok']} "
                f"quality={row['quality']} time={row['elapsed_s']}s "
                f"warnings={len(row['warnings'])}", flush=True,
            )

        failed = [row for row in rows if not row["ok"]]
        if failed:
            for row in failed:
                details = row["hard_failures"] + [str(issue.get("detail") or issue.get("code")) for issue in row.get("preparation_issues") or []]
                print("-", row["id"], ":", " | ".join(details))
            raise SystemExit(f"{len(failed)}/{len(rows)} benchmark scenarios refused or incomplete")
    except Exception as exc:
        suite_error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        meta = {
            "base_url": BASE_URL,
            "expected_sha": EXPECTED_SHA,
            "build_commit": status_payload.get("build_commit"),
            "pipeline_version": status_payload.get("pipeline_version"),
            "release_channel": status_payload.get("release_channel"),
            "scenario_count": len(SCENARIOS),
            "generated_at_epoch": int(time.time()),
            "error": suite_error,
        }
        write_reports(meta, rows)
        if registered:
            try:
                code, deleted, _ = client.json("DELETE", "/auth/account", {
                    "password": password, "confirmation": "SUPPRIMER",
                })
                if code != 200 or deleted.get("deleted") is not True:
                    print(f"WARNING: benchmark account cleanup failed HTTP {code}")
                else:
                    print("Disposable benchmark account removed.")
            except Exception as exc:
                print(f"WARNING: benchmark account cleanup failed: {type(exc).__name__}")

if __name__ == "__main__":
    main()
