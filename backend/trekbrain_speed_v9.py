"""Latency controls for TrekBrain v9.

The route engine used to multiply work: several OSM queries, several geometric
hypotheses, several ORS geometries, then the same again through a retry path.
That is excellent if the product goal is to let the user grow a beard while
waiting.  V9 fast mode keeps the useful diversity but puts hard budgets around
external services and aggressively reuses broad campsite searches.
"""
from __future__ import annotations

import os
import time
from copy import deepcopy
from threading import Lock
from typing import Any

_INSTALLED = False
_STAY_POOL_LOCK = Lock()
_STAY_POOLS: list[dict[str, Any]] = []

_CURRENT_TERMS = (
    "horaire", "horaires", "ouvert", "ouverte", "ouverture", "fermé", "ferme",
    "fermeture", "travaux", "déviation", "deviation", "interdit", "réglement",
    "reglement", "météo", "meteo", "marée", "maree", "train", "gare", "bus",
    "transport", "festival", "fête", "fete", "agenda", "événement", "evenement",
)


def _env_seconds(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _empty_research() -> dict[str, Any]:
    return {
        "provider": None,
        "queries": [],
        "results": [],
        "pages": [],
        "status": "skipped-static-request",
        "elapsed_ms": 0,
        "cache_hits": 0,
        "timed_out_queries": 0,
        "busy_queries": 0,
        "failed_queries": 0,
        "claims_verified": False,
        "free_mode": True,
        "configured_google": False,
        "configured_brave": False,
        "evidence": {"results": 0, "strong_results": 0, "mean_score": 0.0, "pages_read": 0, "topics": {}},
    }


def install_fast_planning(v3, v5, v9) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from . import free_planner_v2 as free
    from . import ors
    from . import trekbrain_roundtrip_v9 as roundtrip

    original_beam = v3._beam_candidates
    original_prompts = v5._candidate_prompts
    original_research = v9.research_request
    original_seconds = v9.seconds
    original_request_json = free._request_json
    original_nearby_stays = roundtrip._nearby_stays

    # ------------------------------------------------------------------
    # 1) Bound OSM latency. Previously one Overpass query could walk through
    #    three servers at 18 seconds each. The planner performs several such
    #    queries, so a slow public service could turn one click into minutes.
    # ------------------------------------------------------------------
    overpass_budget = _env_seconds("TREKBRAIN_OVERPASS_BUDGET_SECONDS", 5.0, 2.0, 10.0)
    overpass_attempt = _env_seconds("TREKBRAIN_OVERPASS_ATTEMPT_SECONDS", 3.0, 1.0, 6.0)
    geocode_timeout = _env_seconds("TREKBRAIN_GEOCODE_TIMEOUT_SECONDS", 4.5, 2.0, 8.0)

    def fast_request_json(url, *, params=None, data=None, timeout=20, ttl=1800, service="service cartographique", retries=2):
        label = str(service or "")
        if label.startswith("Nominatim") or label.startswith("Photon"):
            timeout = min(float(timeout), geocode_timeout)
            retries = 1
        elif label.startswith("Overpass"):
            timeout = min(float(timeout), overpass_attempt)
            retries = 1
        return original_request_json(
            url,
            params=params,
            data=data,
            timeout=timeout,
            ttl=ttl,
            service=service,
            retries=retries,
        )

    free._request_json = fast_request_json

    def fast_overpass(query: str):
        deadline = time.monotonic() + overpass_budget
        errors = []
        # Two independent public mirrors are enough for an interactive request.
        # A third 18-second wait used to add reliability on paper and misery in UI.
        for url in list(free.OVERPASS_URLS)[:2]:
            remaining = deadline - time.monotonic()
            if remaining < 0.65:
                break
            timeout = min(overpass_attempt, max(0.65, remaining))
            try:
                return free._request_json(
                    url,
                    data={"data": query},
                    timeout=timeout,
                    ttl=3600,
                    service=f"Overpass ({url.split('/')[2]})",
                    retries=1,
                )
            except RuntimeError as exc:
                errors.append(str(exc))
        detail = " | ".join(dict.fromkeys(errors))
        raise RuntimeError(
            "OpenStreetMap/Overpass n'a pas répondu dans le budget interactif"
            + (f" : {detail}" if detail else ".")
        )

    # v3 imported these functions by value, while _nearby executes in the free
    # planner module. Patch both namespaces so every v9 OSM path uses one budget.
    free._overpass = fast_overpass
    v3._overpass = fast_overpass

    # ------------------------------------------------------------------
    # 2) Keep only structurally useful route hypotheses. Matrix candidates have
    #    already paid for real walking distances, so routing five lookalikes is
    #    mostly burning ORS time for microscopic score differences.
    # ------------------------------------------------------------------
    def beam_candidates(start, end, center, items, intent, strategy, width=8):
        rows = list(original_beam(start, end, center, items, intent, strategy, width))
        if len(rows) <= 2:
            return rows
        matrix = [c for c in rows if "matrix-loop" in str(getattr(c, "strategy", ""))]
        network = [c for c in rows if "path-network-loop" in str(getattr(c, "strategy", "")) and c not in matrix]
        gr = [c for c in rows if "gr-" in str(getattr(c, "strategy", "")) and c not in network and c not in matrix]
        generic = [c for c in rows if c not in matrix and c not in network and c not in gr]

        selected = []
        for family in (matrix, network, gr, generic):
            if family:
                selected.append(family[0])
            if len(selected) >= 2:
                break
        return selected[:2] or rows[:2]

    # One prompt is the normal path. A second route build is reserved only for a
    # genuinely dated/mandatory side objective where changing geometry matters.
    def candidate_prompts(normalized, targets, compound):
        prompts = list(original_prompts(normalized, targets, compound))
        if len(prompts) <= 1:
            return prompts
        hard_dated = any(
            (t.get("request") or {}).get("target_date")
            or ((t.get("request") or {}).get("required") and (t.get("request") or {}).get("preferred_day"))
            for t in targets
        )
        return prompts[:2] if hard_dated else prompts[:1]

    # ------------------------------------------------------------------
    # 3) Web research does not influence static route geometry. Skip it unless
    #    the request actually depends on current information.
    # ------------------------------------------------------------------
    def research_request(prompt, location, compound, brain_queries=None):
        low = str(prompt or "").casefold()
        side = compound.get("side_requests") or []
        time_sensitive_side = any(x.get("target_date") for x in side if isinstance(x, dict))
        if not time_sensitive_side and not any(term in low for term in _CURRENT_TERMS):
            return _empty_research()
        started = time.monotonic()
        result = original_research(prompt, location, compound, brain_queries)
        result.setdefault("elapsed_ms", round((time.monotonic() - started) * 1000))
        return result

    # v9's second whole geographic hypothesis is useful for offline experiments,
    # but terrible for a 30-second product target. The underlying v3 planner
    # already compares multiple structural candidates. Allow an explicit env var
    # to restore the retry for debugging, otherwise keep it off.
    def fast_seconds(name, default, maximum=None):
        if name == "TREKBRAIN_RETRY_BUDGET_SECONDS" and name not in os.environ:
            return 0.0
        if name == "TREKBRAIN_WEB_BUDGET_SECONDS" and name not in os.environ:
            return 2.5
        return original_seconds(name, default, maximum)

    # ------------------------------------------------------------------
    # 4) Campsite recovery used to run one Overpass request for every probe
    #    around every night. Cache a broad real OSM campsite pool, then filter it
    #    locally for each probe. Four days now means normally one OSM call, not 9.
    # ------------------------------------------------------------------
    def pooled_nearby_stays(v3_module, anchor: dict, category: str, radius_km: float):
        now = time.monotonic()
        requested = max(0.5, float(radius_km))
        broad_radius = min(30.0, max(18.0, requested * 6.0))

        with _STAY_POOL_LOCK:
            _STAY_POOLS[:] = [x for x in _STAY_POOLS if now - float(x.get("created", 0)) < 600]
            pool = None
            for item in reversed(_STAY_POOLS):
                if item.get("category") != category:
                    continue
                center = item["center"]
                centre_distance = roundtrip._haversine(
                    [float(center["lat"]), float(center["lon"])],
                    [float(anchor["lat"]), float(anchor["lon"])],
                )
                # Keep enough margin so the requested local circle is fully
                # contained in the cached broad search.
                if centre_distance + requested + 0.5 <= float(item["radius"]):
                    pool = list(item["rows"])
                    break

        if pool is None:
            pool = list(original_nearby_stays(v3_module, anchor, category, broad_radius))
            with _STAY_POOL_LOCK:
                _STAY_POOLS.append({
                    "created": now,
                    "category": category,
                    "center": {"lat": float(anchor["lat"]), "lon": float(anchor["lon"])},
                    "radius": broad_radius,
                    "rows": deepcopy(pool),
                })
                if len(_STAY_POOLS) > 12:
                    del _STAY_POOLS[:-12]

        out = []
        for stay in pool:
            try:
                distance = roundtrip._haversine(
                    [float(anchor["lat"]), float(anchor["lon"])],
                    [float(stay["lat"]), float(stay["lon"])],
                )
            except Exception:
                continue
            if distance <= requested + 0.15:
                out.append(dict(stay))
        return out

    # ------------------------------------------------------------------
    # 5) ORS normally answers quickly. A dead request must not monopolise 20 s
    #    and then be repeated for snapped/segmented variants. Cap the interactive
    #    calls while retaining the exact same response validation.
    # ------------------------------------------------------------------
    ors_timeout = _env_seconds("TREKBRAIN_ORS_TIMEOUT_SECONDS", 7.0, 3.0, 14.0)
    matrix_timeout = _env_seconds("TREKBRAIN_MATRIX_TIMEOUT_SECONDS", 7.0, 3.0, 14.0)

    def fast_request_route(coords, distance_gps, snap_radius_m=None):
        payload = {
            "coordinates": [[float(p[1]), float(p[0])] for p in coords],
            "instructions": False,
        }
        if snap_radius_m is not None:
            payload["radiuses"] = [int(snap_radius_m)] * len(coords)
        try:
            response = ors.requests.post(
                ors.ORS_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=ors_timeout,
            )
        except ors.requests.Timeout:
            return None, "OpenRouteService : délai interactif dépassé.", None
        except ors.requests.RequestException as exc:
            return None, f"OpenRouteService inaccessible ({exc.__class__.__name__}).", None
        except Exception:
            return None, "Erreur inattendue avec OpenRouteService.", None
        return ors._parse_response(response, coords, distance_gps)

    def fast_distance_matrix(coords):
        if not ors.ORS_API_KEY:
            return {"distances": None, "fallback": True, "warning": "ORS_API_KEY absente."}
        if len(coords) < 2:
            return {"distances": None, "fallback": True, "warning": "Au moins deux points sont nécessaires."}
        coords = coords[:24]
        key = ors._matrix_key(coords)
        now = time.monotonic()
        cached = ors._MATRIX_CACHE.get(key)
        if cached and now - cached[0] < ors._MATRIX_TTL:
            return deepcopy(cached[1])
        payload = {
            "locations": [[float(p[1]), float(p[0])] for p in coords],
            "metrics": ["distance"],
            "units": "km",
            "resolve_locations": False,
        }
        try:
            response = ors.requests.post(
                ors.ORS_MATRIX_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=matrix_timeout,
            )
        except ors.requests.Timeout:
            return {"distances": None, "fallback": True, "warning": "OpenRouteService Matrix : délai interactif dépassé."}
        except ors.requests.RequestException as exc:
            return {"distances": None, "fallback": True, "warning": f"OpenRouteService Matrix inaccessible ({exc.__class__.__name__})."}
        if response.status_code in {401, 403, 429} or response.status_code >= 500 or not response.ok:
            return {"distances": None, "fallback": True, "warning": f"OpenRouteService Matrix HTTP {response.status_code}."}
        try:
            data = response.json()
        except ValueError:
            return {"distances": None, "fallback": True, "warning": "Réponse Matrix JSON invalide."}
        raw = data.get("distances")
        n = len(coords)
        if not isinstance(raw, list) or len(raw) != n or any(not isinstance(row, list) or len(row) != n for row in raw):
            return {"distances": None, "fallback": True, "warning": "Matrice ORS incomplète."}
        distances = []
        for row in raw:
            clean = []
            for value in row:
                try:
                    number = float(value) if value is not None else None
                except (TypeError, ValueError):
                    number = None
                clean.append(round(number, 3) if number is not None and number >= 0 else None)
            distances.append(clean)
        result = {
            "distances": distances,
            "fallback": False,
            "routing_mode": "ors-matrix",
            "profile": ors.ORS_PROFILE,
        }
        ors._MATRIX_CACHE[key] = (now, deepcopy(result))
        while len(ors._MATRIX_CACHE) > 80:
            ors._MATRIX_CACHE.pop(next(iter(ors._MATRIX_CACHE)))
        return result

    def fast_roundtrip_request(start, target_km: float, seed: int):
        if not ors.ORS_API_KEY:
            return None, "OpenRouteService non configuré : ORS_API_KEY est absente du serveur Render."
        payload = {
            "coordinates": [[float(start["lon"]), float(start["lat"])]],
            "instructions": False,
            "options": {"round_trip": {"length": int(round(target_km * 1000)), "points": 6, "seed": int(seed)}},
        }
        try:
            response = ors.requests.post(
                ors.ORS_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=ors_timeout,
            )
        except ors.requests.Timeout:
            return None, "OpenRouteService round-trip : délai interactif dépassé."
        except ors.requests.RequestException as exc:
            return None, f"OpenRouteService round-trip inaccessible ({exc.__class__.__name__})."
        result, warning, _status = ors._parse_response(
            response,
            [[float(start["lat"]), float(start["lon"])]],
            lambda _coords: 0.0,
        )
        if result is None:
            return None, warning or "OpenRouteService n'a pas généré de boucle."
        result["routing_mode"] = "ors-round-trip"
        result["round_trip_seed"] = int(seed)
        return result, None

    def fast_best_roundtrip(start, target_km, daily_min, daily_max, days, v3_module):
        if target_km > 99.0:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Le mode boucle automatique de secours est limité à environ 100 km au total.")
        rows = []
        warnings = []
        for seed in (3, 11):
            route, warning = roundtrip._roundtrip_request(start, target_km, seed)
            if route is None:
                if warning:
                    warnings.append(warning)
                continue
            distance = float(route.get("distance") or 0)
            per_day = distance / max(int(days), 1)
            retrace = float(v3_module._route_retrace_ratio(route.get("coords") or [])) if hasattr(v3_module, "_route_retrace_ratio") else 0.0
            range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
            score = abs(distance - target_km) + range_penalty + retrace * 80
            rows.append((score, route))
            # Healthy first result: stop immediately instead of asking ORS for
            # two cosmetic alternatives.
            if daily_min <= per_day <= daily_max and retrace <= 0.25 and abs(distance - target_km) <= max(4.0, target_km * 0.12):
                return route
        if not rows:
            from fastapi import HTTPException
            detail = warnings[0] if warnings else "OpenRouteService n'a produit aucune boucle pédestre."
            raise HTTPException(status_code=503, detail=detail)
        rows.sort(key=lambda row: row[0])
        return rows[0][1]

    v3._beam_candidates = beam_candidates
    v5._candidate_prompts = candidate_prompts
    v9.research_request = research_request
    v9.seconds = fast_seconds
    roundtrip._nearby_stays = pooled_nearby_stays
    ors._request_route = fast_request_route
    ors.get_distance_matrix = fast_distance_matrix
    roundtrip._roundtrip_request = fast_roundtrip_request
    roundtrip._best_roundtrip = fast_best_roundtrip


__all__ = ["install_fast_planning", "_empty_research"]
