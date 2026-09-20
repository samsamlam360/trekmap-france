"""Latency controls for TrekBrain v9.

The route engine used to multiply work: up to three compound-language prompts,
several beam variants for each, plus Web research even when the answer only
needed static OSM/ORS geometry. This layer keeps useful diversity while removing
redundant expensive work.
"""
from __future__ import annotations

import time
from typing import Any

_INSTALLED = False

_CURRENT_TERMS = (
    "horaire", "horaires", "ouvert", "ouverte", "ouverture", "fermé", "ferme",
    "fermeture", "travaux", "déviation", "deviation", "interdit", "réglement",
    "reglement", "météo", "meteo", "marée", "maree", "train", "gare", "bus",
    "transport", "festival", "fête", "fete", "agenda", "événement", "evenement",
)


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

    original_beam = v3._beam_candidates
    original_prompts = v5._candidate_prompts
    original_research = v9.research_request

    def beam_candidates(start, end, center, items, intent, strategy, width=8):
        rows = list(original_beam(start, end, center, items, intent, strategy, width))
        if len(rows) <= 4:
            return rows
        network = [c for c in rows if "path-network-loop" in str(getattr(c, "strategy", ""))]
        gr = [c for c in rows if "gr-" in str(getattr(c, "strategy", "")) and c not in network]
        generic = [c for c in rows if c not in network and c not in gr]
        # Keep the strongest structurally different hypotheses. v3 later
        # deduplicates them across balanced/scenic/logistics strategies.
        selected = network[:2] + gr[:1] + generic[:1]
        return selected or rows[:4]

    def candidate_prompts(normalized, targets, compound):
        prompts = list(original_prompts(normalized, targets, compound))
        if len(prompts) <= 1:
            return prompts
        # Only a hard dated/required/day-specific objective deserves a second
        # complete route computation. Ordinary nice-to-have POIs are scored on
        # the first route instead of multiplying ORS calls.
        hard = any(
            (t.get("request") or {}).get("required")
            or (t.get("request") or {}).get("target_date")
            or (t.get("request") or {}).get("preferred_day")
            for t in targets
        )
        return prompts[:2] if hard else prompts[:1]

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

    v3._beam_candidates = beam_candidates
    v5._candidate_prompts = candidate_prompts
    # smart_planner_v9 imported research_request by name; replace that module
    # global so _prepare_shared resolves this fast wrapper at call time.
    v9.research_request = research_request


__all__ = ["install_fast_planning"]
