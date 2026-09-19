"""Fast, ranked Web research for TrekBrain v9.

V9 keeps the no-key fallback from v7, runs independent searches in parallel,
deduplicates canonical URLs and ranks search leads without blindly downloading
linked pages. V9.1 adds hiking-logistics coverage (water, overnight stops,
transport and named trails) while keeping a small bounded query budget.
Search text remains untrusted and never becomes route geometry by itself.
"""
from __future__ import annotations

import re
import time
from copy import deepcopy
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from . import web_research_v7 as base
from .trekbrain_runtime_v9 import free_mode, seconds

MAX_QUERIES = 5
MAX_RESULTS = 16
_POOL = ThreadPoolExecutor(max_workers=5, thread_name_prefix="trekbrain-search")
_LOCK = Lock()
_PENDING = {}
_CACHE = {}
MAX_PENDING = 15

_OFFICIAL_HINTS = (
    ".gouv.fr", "service-public.fr", "data.gouv.fr", "france.fr",
    "sncf.com", "sncf-connect.com", "ter.sncf.com", "datatourisme.fr",
    "parcs-naturels-regionaux.fr", "parcnational.fr", "ffrandonnee.fr",
    "ign.fr", "geoportail.gouv.fr",
)
_TOURISM_HINTS = (
    "tourisme", "office-de-tourisme", "destination", "montagnes", "vallee", "vallée",
)
_HIKING_HINTS = (
    "refuges.info", "camptocamp.org", "visorando.com", "altituderando.com",
)
_LOW_TRUST_HINTS = (
    "pinterest.", "facebook.", "instagram.", "tiktok.", "tripadvisor.",
)
_STOP = {
    "avec", "dans", "pour", "une", "des", "les", "sur", "par", "près", "pres",
    "randonnée", "randonnee", "trek", "france", "faire", "voir", "plus", "jour",
}


def _canonical_url(url: str) -> str:
    try:
        p = urlsplit(str(url or ""))
        host = (p.hostname or "").lower()
        if not host or p.scheme.lower() not in {"http", "https"} or p.username or p.password:
            return ""
        path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
        query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}))
        netloc = host + (f":{p.port}" if p.port else "")
        return urlunsplit((p.scheme.lower(), netloc, path, query, ""))
    except Exception:
        return ""


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-zà-ÿ0-9]{3,}", str(value or "").casefold())
    return {w for w in words if w not in _STOP}


def _topic(query: str) -> str:
    low = str(query or "").casefold()
    if any(x in low for x in ("fermet", "réglement", "reglement", "interdit", "bivouac")):
        return "regulation"
    if any(x in low for x in ("fête", "festival", "agenda", "événement", "evenement")):
        return "event"
    if any(x in low for x in ("gare", "bus", "transport", "train", "sncf")):
        return "transport"
    if any(x in low for x in ("camping", "refuge", "gîte", "gite", "hébergement", "hebergement")):
        return "overnight"
    if any(x in low for x in ("eau", "fontaine", "source", "potable")):
        return "water"
    if any(x in low for x in ("gr ", "sentier", "balis", "itinéraire", "itineraire")):
        return "trail"
    return "general"


def source_score(item: dict[str, Any], query: str = "") -> float:
    """Transparent evidence ranking, 0..1. Not a claim of factual truth."""
    try:
        host = (urlsplit(str(item.get("url") or "")).hostname or "").casefold()
    except ValueError:
        host = ""
    text = f"{item.get('title') or ''} {item.get('snippet') or ''}".casefold()
    score = 0.34
    if any(host == h.lstrip(".") or host.endswith("." + h.lstrip(".")) for h in _OFFICIAL_HINTS):
        score += 0.32
    elif any(h in host for h in _TOURISM_HINTS):
        score += 0.18
    elif any(h in host for h in _HIKING_HINTS):
        score += 0.11
    if any(host == h + "com" or host.endswith("." + h + "com") for h in _LOW_TRUST_HINTS):
        score -= 0.18

    q = _tokens(query)
    t = _tokens(text)
    if q:
        overlap = len(q & t) / max(1, min(len(q), 7))
        score += min(0.24, overlap * 0.30)
    if len(str(item.get("snippet") or "")) >= 90:
        score += 0.05
    if any(word in text for word in ("2026", "2027", "horaires", "ouverture", "fermeture", "agenda")):
        score += 0.04
    return round(max(0.05, min(1.0, score)), 3)


def _run_query(query: str, free: bool) -> tuple[str, list[dict[str, str]]]:
    return query, base._duckduckgo_search(query, 5) if free else base.search_web(query, limit=5)


def _finish(key, future):
    try:
        value = future.result()
    except Exception:
        value = None
    with _LOCK:
        _PENDING.pop(key, None)
        if value is not None:
            _CACHE[key] = (time.monotonic(), deepcopy(value))
            while len(_CACHE) > 160:
                _CACHE.pop(next(iter(_CACHE)))


def _resource_queries(location: str) -> list[str]:
    place = re.sub(r"\s+", " ", str(location or "")).strip()
    if not place:
        return []
    return [
        f"{place} randonnée eau potable fontaine source",
        f"{place} randonnée camping refuge gîte",
        f"{place} gare bus train accès randonnée",
        f"{place} GR sentier balisé randonnée",
    ]


def _select_queries(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None) -> list[str]:
    original = base.build_research_queries(prompt, location, compound, brain_queries)
    merged = list(dict.fromkeys([q for q in original + _resource_queries(location) if str(q).strip()]))
    if len(merged) <= MAX_QUERIES:
        return merged

    original_set = set(original)
    def priority(q: str) -> tuple[int, int, int]:
        low = q.casefold()
        topic = _topic(q)
        p = 7
        if topic == "regulation":
            p = 0
        elif topic == "event":
            p = 1
        elif topic == "transport":
            p = 2
        elif topic in {"overnight", "water"}:
            p = 3
        elif topic == "trail":
            p = 4
        elif q in original_set:
            p = 5
        # Prefer a user-derived query when two queries have equal importance.
        return p, 0 if q in original_set else 1, merged.index(q)

    selected = sorted(merged, key=priority)[:MAX_QUERIES]
    # Preserve at least one original query when possible so a specific request
    # is never completely displaced by generic logistics research.
    if original and not any(q in original_set for q in selected):
        selected[-1] = original[0]
    return list(dict.fromkeys(selected))[:MAX_QUERIES]


def research_request(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None = None) -> dict[str, Any]:
    started = time.monotonic()
    queries = _select_queries(prompt, location, compound, brain_queries)
    merged: dict[str, dict[str, Any]] = {}
    completed, futures = [], []
    cache_hits = skipped = errors = 0
    free = free_mode()
    for q in queries:
        key = (free, q.casefold())
        new_future = None
        with _LOCK:
            cached = _CACHE.get(key)
            ttl = 900 if cached and cached[1][1] else 30
            if cached and time.monotonic() - cached[0] < ttl:
                completed.append(deepcopy(cached[1]))
                cache_hits += 1
                continue
            future = _PENDING.get(key)
            if future is None and len(_PENDING) < MAX_PENDING:
                future = new_future = _POOL.submit(_run_query, q, free)
                _PENDING[key] = future
            if future is None:
                skipped += 1
            else:
                futures.append(future)
        if new_future is not None:
            new_future.add_done_callback(lambda f, k=key: _finish(k, f))
    budget = seconds("TREKBRAIN_WEB_BUDGET_SECONDS", 8)
    done, pending = wait(futures, timeout=max(0, budget - (time.monotonic() - started))) if futures else (set(), set())
    for future in done:
        try:
            completed.append(future.result())
        except Exception:
            errors += 1
    for q, items in completed:
        for item in items:
            key = _canonical_url(item.get("url") or "")
            if not key:
                continue
            enriched = dict(
                item,
                url=key,
                query=q,
                topic=_topic(q),
                evidence_score=source_score(item, q),
                evidence_type="search_snippet",
            )
            old = merged.get(key)
            if old is None or (enriched["evidence_score"], q) > (old["evidence_score"], old["query"]):
                merged[key] = enriched

    results = sorted(
        merged.values(),
        key=lambda x: (float(x.get("evidence_score") or 0), len(str(x.get("snippet") or "")), x["url"]),
        reverse=True,
    )[:MAX_RESULTS]
    pages = []

    provider = results[0].get("provider") if results else None
    evidence = [float(x.get("evidence_score") or 0) for x in results]
    by_topic = {}
    for item in results:
        topic = str(item.get("topic") or "general")
        by_topic[topic] = by_topic.get(topic, 0) + 1
    return {
        "provider": provider,
        "queries": queries,
        "results": results,
        "pages": pages,
        "status": "partial" if pending or skipped or errors else "complete" if results else "unavailable",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "cache_hits": cache_hits,
        "timed_out_queries": len(pending),
        "busy_queries": skipped,
        "failed_queries": errors,
        "claims_verified": False,
        "free_mode": free,
        "configured_google": bool(base.os.getenv("GOOGLE_CSE_API_KEY", "").strip() and base.os.getenv("GOOGLE_CSE_CX", "").strip()),
        "configured_brave": bool(base.os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
        "evidence": {
            "results": len(results),
            "strong_results": sum(1 for s in evidence if s >= 0.68),
            "mean_score": round(sum(evidence) / len(evidence), 3) if evidence else 0.0,
            "pages_read": len(pages),
            "topics": by_topic,
        },
    }
