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
        if d > 0:
            distances.append(d)
    target = float(case["daily_km"])
    mean_dev = statistics.fmean(abs(x - target) / target for x in distances) if distances else 1.0
    worst_dev = max((abs(x - target) / target for x in distances), default=1.0)
    if not distances:
        hard.append("aucune distance d'étape exploitable")
    elif mean_dev > 0.35:
        warnings.append(f"écart moyen aux km/jour élevé: {mean_dev*100:.0f}%")
    if worst_dev > 0.55:
        warnings.append(f"une journée s'écarte fortement de la cible: {worst_dev*100:.0f}%")

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
        1 for item in ((result.get("map_resources") or {}).get("points") or [])
        if isinstance(item, dict) and item.get("kind") == "food"
        and item.get("source_url") and item.get("lat") is not None and item.get("lon") is not None
    )
    if case.get("require_food") and food_markers == 0:
        warnings.append("aucun commerce OSM géolocalisé à proximité du tracé")

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

    if elapsed_s > 90:
        warnings.append(f"latence élevée: {elapsed_s:.1f}s")

    return {
        "id": case["id"],
        "ok": not hard,
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
        "closing_gap_km": round(closing, 3) if closing is not None else None,
        "coords": len(coords),
        "water_markers": len(result.get("water") or []),
        "food_markers": food_markers,
        "accommodations": len(result.get("accommodations") or []),
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
    warnings = sum(len(x["warnings"]) for x in rows)
    lines = [
        "# TrekBrain v9 — benchmark production",
        "",
        f"- Build: `{meta.get('build_commit','')[:12]}`",
        f"- Scénarios structurellement valides: **{ok}/{len(rows)}**",
        f"- Qualité moyenne TrekBrain: **{statistics.fmean(qualities):.1f}/100**" if qualities else "- Qualité moyenne: n/a",
        f"- Latence moyenne: **{statistics.fmean(elapsed):.1f} s**",
        f"- Latence max: **{max(elapsed):.1f} s**",
        f"- Avertissements terrain: **{warnings}**",
        "",
        "| Scénario | Statut | Qualité | Temps | Commerces proches | Moteur | Distance | Écart/jour | Alertes |",
        "|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        alerts = "; ".join(row["hard_failures"] + row["warnings"]) or "aucune"
        quality = "n/a" if row["quality"] is None else f"{float(row['quality']):.1f}"
        distance = row["route_distance_km"]
        distance = "n/a" if distance is None else f"{float(distance):.1f} km"
        routing = str(row.get("routing_mode") or row.get("planner_fallback") or "n/a")
        if row.get("fast_roundtrip"):
            routing += " · fast"
        lines.append(
            f"| {row['id']} | {'✅' if row['ok'] else '❌'} | {quality} | {row['elapsed_s']:.1f}s | "
            f"{row.get('food_markers', 0)} | {routing.replace('|','/')} | {distance} | {row['mean_daily_deviation_pct']:.1f}% | "
            f"{alerts.replace('|','/')} |"
        )
    (OUT_DIR / "trekbrain-production-benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    client = Client(BASE_URL)
    suffix = (EXPECTED_SHA[:8] or secrets.token_hex(4)) + "_" + RUN_ID[-8:]
    username = ("trekbench_" + suffix)[:70]
    email = f"{username}@example.invalid"
    password = "Tb!" + secrets.token_urlsafe(24)
    registered = False
    rows = []
    status_payload = {}

    try:
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

        for case in SCENARIOS:
            payload = {k: v for k, v in case.items() if k in {
                "prompt", "region", "days", "daily_km", "difficulty", "route_type",
                "require_transit", "require_water", "require_accommodation", "require_food",
            }}
            ccode, clarify, clarify_s = client.json("POST", "/ai/clarify", payload, timeout=90)
            if ccode != 200:
                clarify = {"needs_clarification": None, "error": clarify, "http": ccode}

            pcode, plan, plan_s = client.json("POST", "/ai/plan", payload, timeout=180)
            if pcode != 200:
                rows.append({
                    "id": case["id"], "ok": False,
                    "hard_failures": [f"/ai/plan HTTP {pcode}: {plan.get('detail', plan)}"],
                    "warnings": [],
                    "elapsed_s": plan_s,
                    "planner_ms": None, "quality": None, "grade": None, "decision_grade": None,
                    "route_type": None, "route_distance_km": None, "stage_distances_km": [],
                    "mean_daily_deviation_pct": 100.0, "worst_daily_deviation_pct": 100.0,
                    "closing_gap_km": None, "coords": 0, "water_markers": 0,
                    "food_markers": 0, "accommodations": 0, "web_sources": 0,
                    "clarification_needed": clarify.get("needs_clarification"),
                    "clarification_questions": clarify.get("questions") or [],
                    "strategy": None, "blockers": [],
                })
                continue

            row = evaluate(case, plan, plan_s, clarify)
            row["clarify_elapsed_s"] = clarify_s
            rows.append(row)
            print(
                f"[{case['id']}] {'OK' if row['ok'] else 'FAIL'} "
                f"quality={row['quality']} time={row['elapsed_s']}s "
                f"warnings={len(row['warnings'])}"
            )

        meta = {
            "base_url": BASE_URL,
            "expected_sha": EXPECTED_SHA,
            "build_commit": status_payload.get("build_commit"),
            "pipeline_version": status_payload.get("pipeline_version"),
            "release_channel": status_payload.get("release_channel"),
            "scenario_count": len(SCENARIOS),
            "generated_at_epoch": int(time.time()),
        }
        write_reports(meta, rows)

        hard = [x for x in rows if not x["ok"]]
        if hard:
            print("\nHard benchmark failures:")
            for row in hard:
                print("-", row["id"], ":", " | ".join(row["hard_failures"]))
            raise SystemExit(f"{len(hard)}/{len(rows)} benchmark scenarios failed structurally")
    finally:
        if registered:
            code, deleted, _ = client.json("DELETE", "/auth/account", {
                "password": password, "confirmation": "SUPPRIMER",
            })
            if code != 200 or deleted.get("deleted") is not True:
                print(f"WARNING: benchmark account cleanup failed HTTP {code}: {deleted}")
            else:
                print("Disposable benchmark account removed.")

if __name__ == "__main__":
    main()
