"""Fast, ranked Web research for TrekBrain v9.

V9 keeps the no-key fallback from v7 but executes independent searches in
parallel, deduplicates canonical URLs and ranks evidence before downloading page
summaries. Search text remains untrusted evidence and never becomes route
geometry by itself.
"""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import web_research_v7 as base

MAX_QUERIES = 4
MAX_RESULTS = 14

_OFFICIAL_HINTS = (
    ".gouv.fr", "service-public.fr", "data.gouv.fr", "france.fr",
    "sncf.com", "sncf-connect.com", "ter.sncf.com", "datatourisme.fr",
    "parcs-naturels-regionaux.fr", "parcnational.fr", "ffrandonnee.fr",
)
_TOURISM_HINTS = (
    "tourisme", "office-de-tourisme", "destination", "montagnes", "vallee", "vallée",
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
        if not host:
            return str(url or "")
        path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
        return urlunsplit((p.scheme.lower() or "https", host, path, "", ""))
    except Exception:
        return str(url or "")


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-zà-ÿ0-9]{3,}", str(value or "").casefold())
    return {w for w in words if w not in _STOP}


def source_score(item: dict[str, Any], query: str = "") -> float:
    """Transparent evidence ranking, 0..1. Not a claim of factual truth."""
    url = str(item.get("url") or "").casefold()
    text = f"{item.get('title') or ''} {item.get('snippet') or ''}".casefold()
    score = 0.34
    if any(h in url for h in _OFFICIAL_HINTS):
        score += 0.32
    elif any(h in url for h in _TOURISM_HINTS):
        score += 0.18
    if any(h in url for h in _LOW_TRUST_HINTS):
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


def _run_query(query: str) -> tuple[str, list[dict[str, str]]]:
    return query, base.search_web(query, limit=5)


def _select_queries(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None) -> list[str]:
    queries = base.build_research_queries(prompt, location, compound, brain_queries)
    if len(queries) <= MAX_QUERIES:
        return queries

    # Dated events, regulations and transport can invalidate a plan, so they
    # take precedence over generic inspiration searches.
    def priority(q: str) -> tuple[int, int]:
        low = q.casefold()
        p = 4
        if any(x in low for x in ("fermet", "réglement", "reglement", "interdit")):
            p = 0
        elif any(x in low for x in ("fête", "festival", "agenda")):
            p = 1
        elif any(x in low for x in ("gare", "bus", "transport")):
            p = 2
        elif any(x in low for x in ("camping", "refuge", "château", "chateau")):
            p = 3
        return p, queries.index(q)

    return sorted(queries, key=priority)[:MAX_QUERIES]


def research_request(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None = None) -> dict[str, Any]:
    queries = _select_queries(prompt, location, compound, brain_queries)
    merged: dict[str, dict[str, Any]] = {}

    # Public search endpoints are latency-bound. Parallel execution cuts the
    # waiting time without increasing the number of requests.
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(queries)))) as pool:
        futures = [pool.submit(_run_query, q) for q in queries]
        for future in as_completed(futures):
            try:
                q, results = future.result()
            except Exception:
                continue
            for item in results:
                key = _canonical_url(item.get("url") or "")
                if not key:
                    continue
                enriched = dict(item)
                enriched["query"] = q
                enriched["evidence_score"] = source_score(enriched, q)
                old = merged.get(key)
                if old is None or enriched["evidence_score"] > old.get("evidence_score", 0):
                    merged[key] = enriched

    results = sorted(
        merged.values(),
        key=lambda x: (float(x.get("evidence_score") or 0), len(str(x.get("snippet") or ""))),
        reverse=True,
    )[:MAX_RESULTS]

    # Read at most three of the strongest pages, also in parallel. Weak/social
    # sources are kept as leads but are not worth extra latency.
    page_candidates = [x for x in results if float(x.get("evidence_score") or 0) >= 0.42][:3]
    pages = []
    if page_candidates:
        with ThreadPoolExecutor(max_workers=len(page_candidates)) as pool:
            jobs = {pool.submit(base.fetch_page_summary, x["url"]): x for x in page_candidates}
            for future in as_completed(jobs):
                item = jobs[future]
                try:
                    summary = future.result()
                except Exception:
                    summary = None
                if summary and (summary.get("description") or summary.get("text")):
                    summary = dict(summary)
                    summary["evidence_score"] = item.get("evidence_score")
                    pages.append(summary)

    provider = results[0].get("provider") if results else None
    evidence = [float(x.get("evidence_score") or 0) for x in results]
    return {
        "provider": provider,
        "queries": queries,
        "results": results,
        "pages": pages,
        "configured_google": bool(base.os.getenv("GOOGLE_CSE_API_KEY", "").strip() and base.os.getenv("GOOGLE_CSE_CX", "").strip()),
        "configured_brave": bool(base.os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
        "evidence": {
            "results": len(results),
            "strong_results": sum(1 for s in evidence if s >= 0.68),
            "mean_score": round(sum(evidence) / len(evidence), 3) if evidence else 0.0,
            "pages_read": len(pages),
        },
    }
