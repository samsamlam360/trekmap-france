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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from threading import Lock
from typing import Any

from . import trekbrain_perf_profile_v9 as perf

_INSTALLED = False
_STAY_POOL_LOCK = Lock()
_STAY_POOLS: list[dict[str, Any]] = []
_MATRIX_AUTH_LOCK = Lock()
_MATRIX_AUTH_STATE: dict[str, Any] = {"until": 0.0, "status": None}

FAST_PLANNING_WRAPPER_VERSION = 3
EXPLICIT_TRAVERSE_PRUNING_VERSION = 1


_CURRENT_TERMS = (
    "horaire", "horaires", "ouvert", "ouverte", "ouverture", "fermé", "ferme",
    "fermeture", "travaux", "déviation", "deviation", "interdit", "réglement",
    "reglement", "météo", "meteo", "marée", "maree",
    "retard", "annulé", "annule", "circulation", "grève", "greve",
    "festival", "fête", "fete", "agenda", "événement", "evenement",
)


def _env_seconds(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _matrix_auth_cooldown_status(now: float | None = None) -> int | None:
    """Return the recent persistent Matrix auth status while its cooldown is active."""
    current = time.monotonic() if now is None else float(now)
    with _MATRIX_AUTH_LOCK:
        if current < float(_MATRIX_AUTH_STATE.get("until") or 0.0):
            try:
                return int(_MATRIX_AUTH_STATE.get("status"))
            except (TypeError, ValueError):
                return 403
        _MATRIX_AUTH_STATE["until"] = 0.0
        _MATRIX_AUTH_STATE["status"] = None
    return None


def _open_matrix_auth_cooldown(status: int) -> None:
    cooldown = _env_seconds(
        "TREKBRAIN_MATRIX_AUTH_COOLDOWN_SECONDS",
        300.0,
        30.0,
        1800.0,
    )
    with _MATRIX_AUTH_LOCK:
        _MATRIX_AUTH_STATE["until"] = max(
            float(_MATRIX_AUTH_STATE.get("until") or 0.0),
            time.monotonic() + cooldown,
        )
        _MATRIX_AUTH_STATE["status"] = int(status)


def _reset_matrix_auth_cooldown() -> None:
    with _MATRIX_AUTH_LOCK:
        _MATRIX_AUTH_STATE["until"] = 0.0
        _MATRIX_AUTH_STATE["status"] = None


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


def _prune_route_candidates(rows, intent):
    """Keep only route families that can materially change an interactive plan."""
    rows = list(rows or [])
    if len(rows) <= 1:
        return rows
    matrix = [c for c in rows if "matrix-loop" in str(getattr(c, "strategy", ""))]
    network = [
        c for c in rows
        if "path-network-loop" in str(getattr(c, "strategy", ""))
        and c not in matrix
    ]
    gr = [
        c for c in rows
        if "gr-" in str(getattr(c, "strategy", ""))
        and c not in network and c not in matrix
    ]
    generic = [c for c in rows if c not in matrix and c not in network and c not in gr]

    selected = []
    for family in (matrix, network, gr, generic):
        if family:
            selected.append(family[0])
        if len(selected) >= 2:
            break

    route_type = str((intent or {}).get("route_type") or "").casefold()
    accommodation = str((intent or {}).get("accommodation") or "").casefold()
    start_query = str((intent or {}).get("start_query") or "").strip()
    end_query = str((intent or {}).get("end_query") or "").strip()

    # When both endpoints are explicit, candidate families differ mostly by
    # optional POI decoration. The route itself is authoritative start -> end
    # and the v3 recovery can split the validated geometry into hiking days.
    # Route only the strongest family instead of paying ORS for a lookalike.
    explicit_traverse = (
        start_query and end_query
        and "boucle" not in route_type
        and "aller-retour" not in route_type
        and "aller retour" not in route_type
    )
    if explicit_traverse and selected:
        return selected[:1]

    # Matrix/network/GR candidates already encode the real multi-day structure.
    # When the user explicitly requests camping/refuge logistics, routing a
    # second lookalike inside the same strategy mostly repeats ORS work. Keep
    # one structural candidate per strategy for loops *and* itinerant routes;
    # the outer planner still compares balanced/scenic/logistics strategies.
    if accommodation in {"camping", "refuge"} and selected:
        return selected[:1]
    return selected[:2] or rows[:2]


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
    original_geocode = v3._geocode

    # ------------------------------------------------------------------
    # 1) Bound OSM latency. Previously one Overpass query could walk through
    #    three servers at 18 seconds each. The planner performs several such
    #    queries, so a slow public service could turn one click into minutes.
    # ------------------------------------------------------------------
    overpass_budget = _env_seconds("TREKBRAIN_OVERPASS_BUDGET_SECONDS", 3.0, 1.5, 8.0)
    overpass_attempt = _env_seconds("TREKBRAIN_OVERPASS_ATTEMPT_SECONDS", 1.8, 1.0, 5.0)
    # Production profiling on 2026-10-04 showed the fallback mirror repeatedly
    # consuming ~2.45-2.57 s and returning no data on every tested loop. Keep
    # the redundancy, but do not let a secondary mirror own the critical path.
    overpass_secondary_attempt = _env_seconds(
        "TREKBRAIN_OVERPASS_SECONDARY_ATTEMPT_SECONDS", 0.85, 0.65, 1.25
    )
    geocode_timeout = _env_seconds("TREKBRAIN_GEOCODE_TIMEOUT_SECONDS", 4.5, 2.0, 8.0)

    def fast_request_json(url, *, params=None, data=None, timeout=20, ttl=1800, service="service cartographique", retries=2, cache_empty=True):
        label = str(service or "")
        if label.startswith("Nominatim") or label.startswith("Photon"):
            timeout = min(float(timeout), geocode_timeout)
            retries = 1
        elif label.startswith("Overpass"):
            timeout = min(float(timeout), overpass_attempt)
            retries = 1

        if label.startswith("Overpass"):
            metric = "overpass.request"
        elif label.startswith("Photon"):
            metric = "photon.request"
        elif label.startswith("Nominatim"):
            metric = "nominatim.request"
        else:
            metric = "geo.request"

        started = time.perf_counter()
        outcome = "ok"
        try:
            return original_request_json(
                url,
                params=params,
                data=data,
                timeout=timeout,
                ttl=ttl,
                service=service,
                retries=retries,
                cache_empty=cache_empty,
            )
        except Exception:
            outcome = "error"
            raise
        finally:
            perf.record(
                metric,
                (time.perf_counter() - started) * 1000,
                service=label,
                timeout_s=round(float(timeout), 2),
                outcome=outcome,
            )

    free._request_json = fast_request_json

    def fast_geocode(query: str, *, nominatim_retries: int = 2):
        """Stagger Nominatim and Photon instead of paying their latency serially."""
        try:
            retry_budget = int(nominatim_retries)
        except (TypeError, ValueError):
            retry_budget = 2
        if retry_budget <= 0:
            return original_geocode(query, nominatim_retries=0)

        errors = []
        nom_rows = []
        photon_rows = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            nom_future = pool.submit(free._geocode_nominatim, query, retries=1)
            try:
                nom_rows = list(nom_future.result(timeout=0.45) or [])
            except FutureTimeoutError:
                photon_future = pool.submit(
                    free._geocode_photon,
                    query,
                    timeout=geocode_timeout,
                    retries=1,
                )
                try:
                    nom_rows = list(nom_future.result() or [])
                except Exception as exc:
                    errors.append(str(exc))
                try:
                    photon_rows = list(photon_future.result() or [])
                except Exception as exc:
                    errors.append(str(exc))
            except Exception as exc:
                errors.append(str(exc))
                try:
                    photon_rows = list(
                        free._geocode_photon(
                            query,
                            timeout=geocode_timeout,
                            retries=1,
                        )
                        or []
                    )
                except Exception as photon_exc:
                    errors.append(str(photon_exc))

        if nom_rows:
            return nom_rows
        if photon_rows:
            return photon_rows
        local = free._local_geocode(query)
        if local:
            return local
        if errors:
            raise RuntimeError(
                "Impossible de localiser la zone. "
                + " | ".join(dict.fromkeys(x for x in errors if x))
            )
        return []

    # v3 imported _geocode by value; replace that module-global reference only
    # for TrekBrain v9's installed fast profile.
    v3._geocode = fast_geocode

    def fast_overpass(query: str, *, max_mirrors: int | None = None):
        deadline = time.monotonic() + overpass_budget
        errors = []
        # Two independent public mirrors are enough for a normal interactive
        # request. Some callers have a safe route fallback and may explicitly
        # cap discovery to the first mirror.
        try:
            mirror_limit = 2 if max_mirrors is None else max(1, min(2, int(max_mirrors)))
        except (TypeError, ValueError):
            mirror_limit = 2
        for mirror_index, url in enumerate(list(free.OVERPASS_URLS)[:mirror_limit]):
            remaining = deadline - time.monotonic()
            if remaining < 0.65:
                break
            attempt_cap = (
                overpass_attempt
                if mirror_index == 0
                else min(overpass_attempt, overpass_secondary_attempt)
            )
            timeout = min(attempt_cap, max(0.65, remaining))
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
        return _prune_route_candidates(rows, intent)

    # One prompt is the normal path. A second route build is reserved only for a
    # genuinely dated/mandatory side objective where changing geometry matters.
    def candidate_prompts(normalized, targets, compound, internal_hint=""):
        # v5 gained an explicit internal_hint argument in v9, but inherited
        # language wrappers can still expose the historical 3-argument API.
        # Preserve compatibility without letting the hint leak into the user
        # constraint parser.
        try:
            prompts = list(original_prompts(normalized, targets, compound, internal_hint))
        except TypeError as exc:
            message = str(exc)
            signature_mismatch = (
                "positional argument" in message
                or "positional arguments" in message
                or "unexpected keyword" in message
            )
            if not signature_mismatch:
                raise
            prompts = list(original_prompts(normalized, targets, compound))
            hint = str(internal_hint or "").strip()
            if hint:
                marker = "\n\nPriorité interne TrekBrain : "
                prompts = [
                    str(prompt or "").rstrip() + marker + hint
                    for prompt in prompts
                ]
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

        if pool is not None:
            perf.mark("lodging.stay_pool", cache_hit=True, category=category)

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
        attempt = perf.next_sequence("ors.directions")
        started = time.perf_counter()
        status = None
        outcome = "ok"
        try:
            response = ors.requests.post(
                ors.ORS_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=ors_timeout,
            )
            status = response.status_code
        except ors.requests.Timeout:
            outcome = "timeout"
            return None, "OpenRouteService : délai interactif dépassé.", None
        except ors.requests.RequestException as exc:
            outcome = exc.__class__.__name__
            return None, f"OpenRouteService inaccessible ({exc.__class__.__name__}).", None
        except Exception as exc:
            outcome = exc.__class__.__name__
            return None, "Erreur inattendue avec OpenRouteService.", None
        finally:
            perf.record(
                "ors.directions",
                (time.perf_counter() - started) * 1000,
                attempt=attempt,
                points=len(coords),
                snapped=snap_radius_m is not None,
                timeout_s=ors_timeout,
                status=status,
                outcome=outcome,
            )
        return ors._parse_response(response, coords, distance_gps)

    def fast_distance_matrix(coords):
        if not ors.ORS_API_KEY:
            return {"distances": None, "fallback": True, "warning": "ORS_API_KEY absente."}
        if len(coords) < 2:
            return {"distances": None, "fallback": True, "warning": "Au moins deux points sont nécessaires."}
        coords = coords[:24]
        blocked_status = _matrix_auth_cooldown_status()
        if blocked_status is not None:
            perf.mark(
                "ors.matrix",
                cache_hit=True,
                outcome="auth-cooldown",
                points=len(coords),
                status=blocked_status,
            )
            return {
                "distances": None,
                "fallback": True,
                "warning": (
                    "OpenRouteService Matrix temporairement ignorée après "
                    f"un refus HTTP {blocked_status} récent."
                ),
            }
        key = ors._matrix_key(coords)
        now = time.monotonic()
        cached = ors._MATRIX_CACHE.get(key)
        if cached and now - cached[0] < ors._MATRIX_TTL:
            perf.mark("ors.matrix", cache_hit=True, outcome="cache", points=len(coords))
            return deepcopy(cached[1])
        payload = {
            "locations": [[float(p[1]), float(p[0])] for p in coords],
            "metrics": ["distance"],
            "units": "km",
            "resolve_locations": False,
        }
        attempt = perf.next_sequence("ors.matrix")
        started = time.perf_counter()
        status = None
        outcome = "ok"
        try:
            response = ors.requests.post(
                ors.ORS_MATRIX_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=matrix_timeout,
            )
            status = response.status_code
        except ors.requests.Timeout:
            outcome = "timeout"
            return {"distances": None, "fallback": True, "warning": "OpenRouteService Matrix : délai interactif dépassé."}
        except ors.requests.RequestException as exc:
            outcome = exc.__class__.__name__
            return {"distances": None, "fallback": True, "warning": f"OpenRouteService Matrix inaccessible ({exc.__class__.__name__})."}
        finally:
            perf.record(
                "ors.matrix",
                (time.perf_counter() - started) * 1000,
                attempt=attempt,
                points=len(coords),
                timeout_s=matrix_timeout,
                status=status,
                outcome=outcome,
            )
        if response.status_code in {401, 403}:
            _open_matrix_auth_cooldown(response.status_code)
            return {"distances": None, "fallback": True, "warning": f"OpenRouteService Matrix HTTP {response.status_code}."}
        if response.status_code == 429 or response.status_code >= 500 or not response.ok:
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
        attempt = perf.next_sequence("ors.roundtrip")
        started = time.perf_counter()
        status = None
        outcome = "ok"
        try:
            response = ors.requests.post(
                ors.ORS_URL,
                json=payload,
                headers={"Authorization": ors.ORS_API_KEY, "Content-Type": "application/json"},
                timeout=ors_timeout,
            )
            status = response.status_code
        except ors.requests.Timeout:
            outcome = "timeout"
            return None, "OpenRouteService round-trip : délai interactif dépassé."
        except ors.requests.RequestException as exc:
            outcome = exc.__class__.__name__
            return None, f"OpenRouteService round-trip inaccessible ({exc.__class__.__name__})."
        finally:
            perf.record(
                "ors.roundtrip",
                (time.perf_counter() - started) * 1000,
                attempt=attempt,
                target_km=round(float(target_km), 1),
                seed=int(seed),
                timeout_s=ors_timeout,
                status=status,
                outcome=outcome,
            )
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
        attempt_rows = []
        requested_km = float(target_km)
        for attempt, seed in enumerate((3, 11)):
            route, warning = roundtrip._roundtrip_request(start, requested_km, seed)
            if route is None:
                if warning:
                    warnings.append(warning)
                continue
            distance = float(route.get("distance") or 0)
            per_day = distance / max(int(days), 1)
            retrace = float(v3_module._route_retrace_ratio(route.get("coords") or [])) if hasattr(v3_module, "_route_retrace_ratio") else 0.0
            range_penalty = max(0.0, daily_min - per_day) * 5 + max(0.0, per_day - daily_max) * 8
            score = abs(distance - target_km) + range_penalty + retrace * 80
            candidate = dict(route)
            candidate["round_trip_requested_km"] = round(requested_km, 2)
            candidate["round_trip_target_km"] = round(float(target_km), 2)
            candidate["round_trip_retrace_ratio"] = round(float(retrace), 4)
            attempt_rows.append({
                "seed": int(seed),
                "requested_km": round(float(requested_km), 2),
                "returned_km": round(float(distance), 2),
                "retrace": round(float(retrace), 4),
            })
            rows.append((score, candidate))
            # Stop after one ORS call only when the route is already close to
            # the requested target, not merely inside the broad +/-25% safety
            # tolerance. The broad window is useful for feasibility, but using it
            # as an early-exit criterion degraded Vercors from ~15.1 to ~18.7
            # km/day even though the corrective second call produced a much
            # better loop.
            if (
                daily_min <= per_day <= daily_max
                and retrace <= 0.25
                and abs(distance - target_km) <= max(4.0, target_km * 0.12)
            ):
                candidate["round_trip_attempt_count"] = len(attempt_rows)
                candidate["round_trip_attempts"] = list(attempt_rows)
                candidate["candidate_pool_size"] = 1
                candidate["candidate_modes"] = ["ors-round-trip"]
                candidate["candidate_summary"] = [{
                    "mode": "ors-round-trip",
                    "km": round(float(distance), 1),
                    "requested_km": candidate.get("round_trip_requested_km"),
                    "retrace": candidate.get("round_trip_retrace_ratio"),
                }]
                candidate["fast_ranked"] = True
                return candidate

            # Keep the same two-call budget, but make the second call corrective.
            # ORS round_trip can systematically overshoot or undershoot on a
            # constrained path network. Scale its requested length from the
            # measured first result instead of merely changing the random seed.
            if attempt == 0 and distance > 0:
                correction = float(target_km) / distance
                correction = max(0.72, min(1.28, correction))
                requested_km = max(6.0, min(99.0, float(target_km) * correction))
        if not rows:
            from fastapi import HTTPException
            detail = warnings[0] if warnings else "OpenRouteService n'a produit aucune boucle pédestre."
            raise HTTPException(status_code=503, detail=detail)
        # Distance accuracy outranks a modest retrace difference when the
        # corrective ORS attempt is materially closer to the user's target.
        # This keeps the same two network calls while avoiding cases where the
        # historical retrace*80 term preferred a ~28% oversized loop.
        precision_limit = max(4.0, float(target_km) * 0.18)
        precision_rows = [
            row for row in rows
            if abs(float(row[1].get("distance") or 0) - float(target_km)) <= precision_limit
            and float(row[1].get("round_trip_retrace_ratio") or 0.0) <= 0.30
        ]
        if precision_rows:
            precision_rows.sort(key=lambda row: (
                abs(float(row[1].get("distance") or 0) - float(target_km)),
                float(row[1].get("round_trip_retrace_ratio") or 0.0),
                row[0],
            ))
            selected = precision_rows[0][1]
            selected["distance_precision_preferred"] = True
        else:
            rows.sort(key=lambda row: row[0])
            selected = rows[0][1]

        # _recover_unranked_oversized_roundtrip exists for raw ORS routes that
        # bypassed candidate ranking. fast_best_roundtrip has already compared
        # up to two real ORS variants, so mark the selected result as ranked
        # when it also fits the *final* soft stage ceiling. Otherwise leave the
        # metadata absent so the deeper recovery can still rescue a genuinely
        # oversized route.
        selected_distance = float(selected.get("distance") or 0)
        selected_per_day = selected_distance / max(int(days), 1)
        target_per_day = float(target_km) / max(int(days), 1)
        soft_window = float(daily_max) >= target_per_day * 1.20 - 0.05
        final_slack = 0.75 if soft_window else 0.35
        if (
            selected_per_day >= float(daily_min) * 0.90
            and selected_per_day <= float(daily_max) + final_slack
        ):
            selected["candidate_pool_size"] = len(rows)
            selected["candidate_modes"] = sorted({
                str(row[1].get("routing_mode") or "unknown") for row in rows
            })
            selected["candidate_summary"] = [
                {
                    "mode": str(candidate.get("routing_mode") or "unknown"),
                    "km": round(float(candidate.get("distance") or 0), 1),
                    "requested_km": candidate.get("round_trip_requested_km"),
                    "retrace": candidate.get("round_trip_retrace_ratio"),
                }
                for _score, candidate in rows
            ]
            selected["fast_ranked"] = True
        selected["round_trip_attempt_count"] = len(attempt_rows)
        selected["round_trip_attempts"] = list(attempt_rows)
        return selected

    v3._beam_candidates = beam_candidates
    v5._candidate_prompts = candidate_prompts
    v9.research_request = research_request
    v9.seconds = fast_seconds
    roundtrip._nearby_stays = pooled_nearby_stays
    ors._request_route = fast_request_route
    ors.get_distance_matrix = fast_distance_matrix
    roundtrip._roundtrip_request = fast_roundtrip_request
    roundtrip._best_roundtrip = fast_best_roundtrip


__all__ = ["install_fast_planning", "_empty_research", "_prune_route_candidates"]
