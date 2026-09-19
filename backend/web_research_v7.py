"""Web research layer for TrekMap Agent v7.

Provider order:
1. Google Programmable Search when explicitly configured.
2. Brave Search API when explicitly configured.
3. DuckDuckGo HTML as a no-key, best-effort fallback.

The planner never trusts search text as route geometry. Results are evidence and
ideas only; geographic waypoints still have to be validated by the geodata layer.
"""
from __future__ import annotations

import html
import os
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

USER_AGENT = os.getenv("TREKMAP_USER_AGENT", "TrekMap-France/7.0 (+https://trekmap-france.onrender.com)")
TIMEOUT = 10
_CACHE: dict[str, tuple[float, Any]] = {}


class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "a" and "result__a" in cls:
            href = attrs.get("href", "")
            self._current = {"title": "", "url": _clean_ddg_url(href), "snippet": ""}
            self._capture_title = True
        elif self._current is not None and tag in {"a", "div", "span"} and "result__snippet" in cls:
            self._capture_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._capture_title:
            self._capture_title = False
        if self._capture_snippet and tag in {"a", "div", "span"}:
            self._capture_snippet = False
            if self._current and self._current.get("title") and self._current.get("url"):
                self.results.append(self._current)
                self._current = None

    def handle_data(self, data):
        if self._current is None:
            return
        clean = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not clean:
            return
        if self._capture_title:
            self._current["title"] += (" " if self._current["title"] else "") + clean
        elif self._capture_snippet:
            self._current["snippet"] += (" " if self._current["snippet"] else "") + clean


class _PageTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.text: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "meta":
            name = str(attrs.get("name") or attrs.get("property") or "").casefold()
            if name in {"description", "og:description"} and not self.description:
                self.description = re.sub(r"\s+", " ", html.unescape(str(attrs.get("content") or ""))).strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        clean = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not clean:
            return
        if self._in_title:
            self.title += (" " if self.title else "") + clean
        elif len(" ".join(self.text)) < 5000:
            self.text.append(clean)


def _clean_ddg_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return url


def _cache_get(key: str, ttl: int = 1800):
    item = _CACHE.get(key)
    if item and time.time() - item[0] < ttl:
        return item[1]
    return None


def _cache_put(key: str, value: Any):
    _CACHE[key] = (time.time(), value)
    if len(_CACHE) > 300:
        for old_key, _ in sorted(_CACHE.items(), key=lambda x: x[1][0])[:80]:
            _CACHE.pop(old_key, None)


def _normalise_result(item: dict[str, Any], provider: str) -> dict[str, str] | None:
    title = re.sub(r"\s+", " ", html.unescape(str(item.get("title") or ""))).strip()[:240]
    url = str(item.get("url") or item.get("link") or "").strip()
    snippet = re.sub(r"\s+", " ", html.unescape(str(item.get("snippet") or item.get("description") or ""))).strip()[:900]
    if not title or not url.startswith(("http://", "https://")):
        return None
    return {"title": title, "url": url, "snippet": snippet, "provider": provider}


def _google_search(query: str, limit: int) -> list[dict[str, str]]:
    key = os.getenv("GOOGLE_CSE_API_KEY", "").strip()
    cx = os.getenv("GOOGLE_CSE_CX", "").strip()
    if not key or not cx:
        return []
    r = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": query, "num": min(limit, 10), "hl": "fr", "gl": "fr", "safe": "active"},
        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for item in (r.json().get("items") or []):
        normal = _normalise_result(item, "Google")
        if normal:
            out.append(normal)
    return out


def _brave_search(query: str, limit: int) -> list[dict[str, str]]:
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        return []
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": min(limit, 10), "country": "fr", "search_lang": "fr", "safesearch": "moderate"},
        headers={"Accept": "application/json", "X-Subscription-Token": key, "User-Agent": USER_AGENT}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for item in (((r.json().get("web") or {}).get("results")) or []):
        normal = _normalise_result(item, "Brave")
        if normal:
            out.append(normal)
    return out


def _duckduckgo_search(query: str, limit: int) -> list[dict[str, str]]:
    r = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query, "kl": "fr-fr"},
        headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    parser = _DDGParser()
    parser.feed(r.text)
    out = []
    for item in parser.results:
        normal = _normalise_result(item, "DuckDuckGo")
        if normal:
            out.append(normal)
        if len(out) >= limit:
            break
    return out


def search_web(query: str, limit: int = 5) -> list[dict[str, str]]:
    query = re.sub(r"\s+", " ", str(query or "")).strip()[:350]
    if not query:
        return []
    key = "search:" + query.casefold()
    cached = _cache_get(key)
    if cached is not None:
        return cached

    providers = (_google_search, _brave_search, _duckduckgo_search)
    for provider in providers:
        try:
            results = provider(query, max(1, min(limit, 8)))
        except Exception:
            continue
        if results:
            _cache_put(key, results)
            return results
    _cache_put(key, [])
    return []


def fetch_page_summary(url: str) -> dict[str, str] | None:
    """Fetch a tiny public-page summary. Search text is untrusted evidence only."""
    if not str(url).startswith(("http://", "https://")):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if not host or host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return None
    key = "page:" + url
    cached = _cache_get(key, 3600)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "fr-FR,fr;q=0.9"}, timeout=8, allow_redirects=True)
        r.raise_for_status()
        if "text/html" not in (r.headers.get("content-type") or ""):
            return None
        parser = _PageTextParser()
        parser.feed(r.text[:600_000])
        text_value = re.sub(r"\s+", " ", " ".join(parser.text)).strip()[:2600]
        result = {"title": parser.title[:240], "description": parser.description[:700], "text": text_value, "url": r.url}
        _cache_put(key, result)
        return result
    except Exception:
        return None


def build_research_queries(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None = None) -> list[str]:
    queries: list[str] = []
    for q in brain_queries or []:
        q = re.sub(r"\s+", " ", str(q)).strip()
        if q:
            queries.append(q)
    for req in compound.get("side_requests") or []:
        kind = req.get("kind")
        target_date = req.get("target_date") or ""
        if kind == "event":
            queries.append(f"fête festival agenda {location} {target_date}".strip())
        elif kind == "castle":
            queries.append(f"château visite {location} randonnée")
        elif kind == "village":
            queries.append(f"village remarquable {location} randonnée")
        elif kind == "food_local":
            queries.append(f"marché spécialité locale {location}")
    folded = prompt.casefold()
    if any(x in folded for x in ("camping", "refuge", "dormir", "nuit")):
        queries.append(f"camping refuge randonnée {location}")
    if any(x in folded for x in ("train", "gare", "bus", "transport")):
        queries.append(f"gare bus accès randonnée {location}")
    if any(x in folded for x in ("fermet", "interdit", "reglement", "réglement", "reserve", "réserve")):
        queries.append(f"réglementation randonnée fermeture sentier {location}")
    queries.append(f"randonnée trek lieux à voir {location}")
    # Preserve order, bound external traffic.
    unique = []
    seen = set()
    for q in queries:
        key = q.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(q[:300])
    return unique[:6]


def research_request(prompt: str, location: str, compound: dict[str, Any], brain_queries: list[str] | None = None) -> dict[str, Any]:
    queries = build_research_queries(prompt, location, compound, brain_queries)
    all_results: list[dict[str, str]] = []
    seen_urls = set()
    for q in queries:
        for item in search_web(q, limit=4):
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            enriched = dict(item)
            enriched["query"] = q
            all_results.append(enriched)
            if len(all_results) >= 18:
                break
        if len(all_results) >= 18:
            break

    # Fetch only two pages. Search snippets remain enough for the rest and this
    # keeps the free service polite and reasonably fast.
    page_summaries = []
    for item in all_results[:4]:
        if len(page_summaries) >= 2:
            break
        summary = fetch_page_summary(item["url"])
        if summary and (summary.get("description") or summary.get("text")):
            page_summaries.append(summary)

    provider = all_results[0]["provider"] if all_results else None
    return {
        "provider": provider,
        "queries": queries,
        "results": all_results,
        "pages": page_summaries,
        "configured_google": bool(os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_CX", "").strip()),
        "configured_brave": bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip()),
    }
