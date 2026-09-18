"""TrekMap AI planner.

Agentic trek preparation built on the OpenAI Responses API. The model chooses
places and explains trade-offs, while coordinates and route geometry come from
deterministic geodata/routing tools.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict, deque
from typing import Any

import requests
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from . import ors

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - lets the app boot with a clear status
    OpenAI = None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "90"))
AI_MAX_TOOL_ROUNDS = 8
AI_RATE_WINDOW = 60
AI_RATE_LIMIT = 4

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = os.getenv(
    "TREKMAP_USER_AGENT",
    "TrekMap-France/5.0 (+https://trekmap-france.onrender.com)",
)

_ai_hits: dict[int, deque[float]] = defaultdict(deque)


class AIPlanRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=4000)
    region: str = Field(default="", max_length=120)
    days: int = Field(default=3, ge=1, le=21)
    daily_km: float = Field(default=18, ge=3, le=40)
    difficulty: str = Field(default="medium", max_length=20)
    route_type: str = Field(default="Boucle", max_length=30)
    require_transit: bool = True
    require_water: bool = True
    require_accommodation: bool = True
    require_food: bool = True
    current_plan: dict[str, Any] | None = None


def _rate_limit(user_id: int) -> None:
    now = time.monotonic()
    q = _ai_hits[int(user_id)]
    while q and now - q[0] > AI_RATE_WINDOW:
        q.popleft()
    if len(q) >= AI_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Trop de demandes IA. Attends environ une minute avant de relancer une préparation.",
        )
    q.append(now)


def _request_json(url: str, *, params=None, data=None, timeout=20) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        if data is None:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, data=data, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.Timeout as exc:
        raise RuntimeError("Le service géographique a dépassé le délai d'attente.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Service géographique indisponible ({exc.__class__.__name__}).") from exc
    except ValueError as exc:
        raise RuntimeError("Le service géographique a renvoyé une réponse invalide.") from exc


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(1 - h, 0)))


def _trusted(trusted_points: list[tuple[float, float]], lat: float, lon: float, radius_m=350) -> bool:
    return any(_distance_km((lat, lon), p) * 1000 <= radius_m for p in trusted_points)


def _add_trusted(trusted_points: list[tuple[float, float]], lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return
    if not _trusted(trusted_points, lat, lon, radius_m=30):
        trusted_points.append((lat, lon))


def _geocode(query: str, trusted_points: list[tuple[float, float]], limit: int = 5) -> dict[str, Any]:
    query = " ".join(str(query or "").split())[:240]
    if not query:
        return {"items": [], "warning": "Recherche vide."}
    data = _request_json(
        NOMINATIM_URL,
        params={
            "q": query,
            "format": "jsonv2",
            "limit": max(1, min(int(limit or 5), 6)),
            "addressdetails": 1,
            "countrycodes": "fr",
        },
        timeout=15,
    )
    items = []
    for row in data if isinstance(data, list) else []:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        _add_trusted(trusted_points, lat, lon)
        items.append(
            {
                "name": row.get("display_name", "")[:300],
                "lat": lat,
                "lon": lon,
                "type": row.get("type") or row.get("class") or "place",
                "osm_type": row.get("osm_type"),
                "osm_id": row.get("osm_id"),
            }
        )
    return {"items": items}


CATEGORY_FILTERS = {
    "water": [
        '["amenity"="drinking_water"]',
        '["man_made"="water_tap"]',
        '["natural"="spring"]',
    ],
    "camping": [
        '["tourism"="camp_site"]',
        '["tourism"="caravan_site"]',
    ],
    "refuge": [
        '["tourism"="alpine_hut"]',
        '["tourism"="wilderness_hut"]',
        '["amenity"="shelter"]',
    ],
    "food": [
        '["shop"="supermarket"]',
        '["shop"="convenience"]',
        '["shop"="bakery"]',
        '["amenity"="restaurant"]',
        '["amenity"="cafe"]',
    ],
    "transit": [
        '["railway"="station"]',
        '["railway"="halt"]',
        '["highway"="bus_stop"]',
        '["public_transport"="station"]',
    ],
    "viewpoint": [
        '["tourism"="viewpoint"]',
        '["natural"="peak"]',
        '["natural"="waterfall"]',
    ],
}


def _water_status(tags: dict[str, Any]) -> str:
    if tags.get("amenity") == "drinking_water" or tags.get("drinking_water") == "yes":
        return "potable_referenced"
    if tags.get("drinking_water") == "no":
        return "not_potable"
    return "unverified"


def _search_nearby(
    lat: float,
    lon: float,
    radius_km: float,
    categories: list[str],
    trusted_points: list[tuple[float, float]],
) -> dict[str, Any]:
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"items": [], "warning": "Centre de recherche invalide."}
    radius_m = max(250, min(int(float(radius_km or 5) * 1000), 30000))
    requested = [c for c in categories if c in CATEGORY_FILTERS] or ["water", "camping", "refuge", "food", "transit", "viewpoint"]
    clauses = []
    for category in requested:
        for tag_filter in CATEGORY_FILTERS[category]:
            clauses.append(f"nwr(around:{radius_m},{lat},{lon}){tag_filter};")
    query = "[out:json][timeout:20];(" + "".join(clauses) + ");out center tags 80;"
    data = _request_json(OVERPASS_URL, data={"data": query}, timeout=25)
    items = []
    for element in (data.get("elements") or [])[:80]:
        tags = element.get("tags") or {}
        e_lat = element.get("lat")
        e_lon = element.get("lon")
        if e_lat is None or e_lon is None:
            center = element.get("center") or {}
            e_lat, e_lon = center.get("lat"), center.get("lon")
        try:
            e_lat, e_lon = float(e_lat), float(e_lon)
        except (TypeError, ValueError):
            continue
        _add_trusted(trusted_points, e_lat, e_lon)
        category = "other"
        if tags.get("amenity") == "drinking_water" or tags.get("man_made") == "water_tap" or tags.get("natural") == "spring":
            category = "water"
        elif tags.get("tourism") in {"camp_site", "caravan_site"}:
            category = "camping"
        elif tags.get("tourism") in {"alpine_hut", "wilderness_hut"} or tags.get("amenity") == "shelter":
            category = "refuge"
        elif tags.get("railway") in {"station", "halt"} or tags.get("highway") == "bus_stop" or tags.get("public_transport") == "station":
            category = "transit"
        elif tags.get("shop") in {"supermarket", "convenience", "bakery"} or tags.get("amenity") in {"restaurant", "cafe"}:
            category = "food"
        elif tags.get("tourism") == "viewpoint" or tags.get("natural") in {"peak", "waterfall"}:
            category = "viewpoint"
        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        item = {
            "name": tags.get("name") or tags.get("ref") or f"{category.title()} OSM",
            "category": category,
            "lat": e_lat,
            "lon": e_lon,
            "distance_from_center_km": round(_distance_km((lat, lon), (e_lat, e_lon)), 2),
            "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else "",
        }
        if category == "water":
            item["water_status"] = _water_status(tags)
        if tags.get("website"):
            item["website"] = tags.get("website")
        if tags.get("opening_hours"):
            item["opening_hours"] = tags.get("opening_hours")
        items.append(item)
    items.sort(key=lambda x: x.get("distance_from_center_km", 9999))
    return {"items": items[:60], "count": min(len(items), 60)}


def _route(
    waypoints: list[dict[str, Any]],
    trusted_points: list[tuple[float, float]],
    legacy_main,
) -> dict[str, Any]:
    coords: list[list[float]] = []
    for p in waypoints:
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "Coordonnées de waypoint invalides."}
        if not _trusted(trusted_points, lat, lon):
            return {
                "ok": False,
                "error": "Un waypoint n'est pas issu d'un outil géographique vérifié. Recherche d'abord ce lieu avec geocode_place ou search_nearby.",
            }
        coords.append([lat, lon])
    if not 2 <= len(coords) <= 30:
        return {"ok": False, "error": "Le calcul nécessite entre 2 et 30 waypoints."}
    result = ors.get_route(coords, legacy_main.distance_gps)
    route_coords = result.get("coords") or coords
    elevation = legacy_main.elevation_gain(route_coords)
    return {
        "ok": True,
        "distance_km": float(result.get("distance") or 0),
        "elevation_gain_m": int(elevation or 0),
        "fallback": bool(result.get("fallback")),
        "warning": result.get("warning"),
    }


def _downsample(coords: list[list[float]], max_points: int = 2500) -> list[list[float]]:
    if len(coords) <= max_points:
        return coords
    step = (len(coords) - 1) / (max_points - 1)
    return [coords[round(i * step)] for i in range(max_points)]


def _place_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "access_note": {"type": "string"},
        },
        "required": ["name", "lat", "lon", "access_note"],
        "additionalProperties": False,
    }


def _plan_schema() -> dict[str, Any]:
    point = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["name", "lat", "lon", "reason"],
        "additionalProperties": False,
    }
    stage = {
        "type": "object",
        "properties": {
            "day": {"type": "integer"},
            "title": {"type": "string"},
            "from_name": {"type": "string"},
            "to_name": {"type": "string"},
            "distance_km": {"type": "number"},
            "elevation_gain_m": {"type": "integer"},
            "overnight": {"type": "string"},
            "water_notes": {"type": "string"},
            "food_notes": {"type": "string"},
            "highlights": {"type": "array", "items": {"type": "string"}},
            "safety_notes": {"type": "string"},
        },
        "required": [
            "day", "title", "from_name", "to_name", "distance_km", "elevation_gain_m",
            "overnight", "water_notes", "food_notes", "highlights", "safety_notes",
        ],
        "additionalProperties": False,
    }
    poi = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "source_url": {"type": "string"},
        },
        "required": ["name", "type", "lat", "lon", "source_url"],
        "additionalProperties": False,
    }
    water = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "status": {"type": "string", "enum": ["potable_referenced", "unverified", "not_potable"]},
            "notes": {"type": "string"},
            "source_url": {"type": "string"},
        },
        "required": ["name", "lat", "lon", "status", "notes", "source_url"],
        "additionalProperties": False,
    }
    accommodation = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "notes": {"type": "string"},
            "source_url": {"type": "string"},
        },
        "required": ["name", "type", "lat", "lon", "notes", "source_url"],
        "additionalProperties": False,
    }
    source = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "purpose": {"type": "string"},
        },
        "required": ["title", "url", "purpose"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "region": {"type": "string"},
            "summary": {"type": "string"},
            "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            "route_type": {"type": "string", "enum": ["Boucle", "Aller-retour", "Traversée", "Itinérance"]},
            "best_season": {"type": "string"},
            "duration_days": {"type": "integer"},
            "start": _place_schema(),
            "end": _place_schema(),
            "waypoints": {"type": "array", "items": point},
            "stages": {"type": "array", "items": stage},
            "points_of_interest": {"type": "array", "items": poi},
            "water": {"type": "array", "items": water},
            "accommodations": {"type": "array", "items": accommodation},
            "transport": {
                "type": "object",
                "properties": {
                    "outbound": {"type": "string"},
                    "return": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["outbound", "return", "notes"],
                "additionalProperties": False,
            },
            "confidence": {
                "type": "object",
                "properties": {
                    "overall": {"type": "string", "enum": ["high", "medium", "low"]},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["overall", "limitations"],
                "additionalProperties": False,
            },
            "sources": {"type": "array", "items": source},
        },
        "required": [
            "title", "region", "summary", "difficulty", "route_type", "best_season",
            "duration_days", "start", "end", "waypoints", "stages",
            "points_of_interest", "water", "accommodations", "transport",
            "confidence", "sources",
        ],
        "additionalProperties": False,
    }


TOOLS = [
    {"type": "web_search"},
    {
        "type": "function",
        "name": "geocode_place",
        "description": "Find real places in France and return verified coordinates. Call this before using a named place as a route waypoint.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 6},
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_nearby",
        "description": "Search OpenStreetMap around verified coordinates for water, camping, refuges, food, public transport and viewpoints.",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radius_km": {"type": "number", "minimum": 0.25, "maximum": 30},
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["water", "camping", "refuge", "food", "transit", "viewpoint"]},
                },
            },
            "required": ["lat", "lon", "radius_km", "categories"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "calculate_hiking_route",
        "description": "Calculate a real pedestrian route with OpenRouteService between verified waypoints and return authoritative distance/elevation statistics.",
        "parameters": {
            "type": "object",
            "properties": {
                "waypoints": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 30,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                        },
                        "required": ["name", "lat", "lon"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["waypoints"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "finalize_trek_plan",
        "description": "Return the final TrekMap plan only after places, route, logistics and current web information have been checked.",
        "parameters": _plan_schema(),
        "strict": True,
    },
]


INSTRUCTIONS = """You are TrekMap AI, a meticulous hiking-trip planning agent for France.

Your job is to prepare realistic hiking treks, not to improvise attractive-sounding routes.

NON-NEGOTIABLE DATA RULES
- Never invent coordinates. Every final waypoint coordinate must come from geocode_place or search_nearby.
- Always call calculate_hiking_route before finalizing. Route distance/elevation from tools override your estimates.
- Use web search for current access, transport, accommodation availability, closures/restrictions and official/local information.
- Never invent opening dates, timetables, reservations, potable water or trail status.
- A spring, stream or tap without drinking_water=yes is NOT confirmed potable. Mark it unverified.
- Prefer official/marked hiking paths and ordinary pedestrian routes.
- Do not propose off-trail travel, glacier travel, via ferrata, climbing, canyoning, hazardous river crossings, closed/restricted routes or routes requiring specialist equipment.
- If current conditions or legality cannot be verified, state the limitation and recommend checking the cited authority before departure.
- Public transport details must be sourced/current; otherwise describe only the nearby station/stop and say schedules need confirmation.
- Keep the final waypoint list efficient (normally 2-12 points, never more than 30).

PLANNING QUALITY
- Balance stages using distance AND elevation, not distance alone.
- Check water, overnight options, food/resupply, start/end transport and interesting places.
- For a loop, start and end should be the same practical place or extremely close.
- For a traverse, verify return transport.
- If the user's request is incompatible with a safe, credible hike, produce a safer hiking alternative and explain the limitation.
- Sources must be genuine URLs seen in tool/web results. Do not fabricate URLs.

FINALIZATION
- Your final action MUST be finalize_trek_plan.
- Include concise safety_notes and confidence limitations.
- Use difficulty easy/medium/hard only.
"""


def _build_user_prompt(data: AIPlanRequest) -> str:
    constraints = {
        "region": data.region,
        "days": data.days,
        "target_daily_km": data.daily_km,
        "difficulty": data.difficulty,
        "route_type": data.route_type,
        "require_transit": data.require_transit,
        "require_water": data.require_water,
        "require_accommodation": data.require_accommodation,
        "require_food": data.require_food,
    }
    text = (
        "Prépare un trek en France à partir de cette demande utilisateur:\n"
        f"{data.prompt}\n\nContraintes structurées:\n{json.dumps(constraints, ensure_ascii=False)}"
    )
    if data.current_plan:
        current = json.dumps(data.current_plan, ensure_ascii=False)
        if len(current) > 50000:
            current = current[:50000]
        text += (
            "\n\nL'utilisateur modifie un plan déjà proposé. Conserve ce qui reste pertinent, "
            "revalide les éléments changés et réponds à la nouvelle demande. Plan actuel:\n"
            + current
        )
    return text


def _execute_tool(name: str, args: dict[str, Any], trusted_points, legacy_main):
    if name == "geocode_place":
        return _geocode(args.get("query", ""), trusted_points, args.get("limit", 5))
    if name == "search_nearby":
        return _search_nearby(
            args.get("lat"), args.get("lon"), args.get("radius_km", 5),
            args.get("categories") or [], trusted_points,
        )
    if name == "calculate_hiking_route":
        return _route(args.get("waypoints") or [], trusted_points, legacy_main)
    raise RuntimeError(f"Outil inconnu: {name}")


def _validate_and_enrich_plan(plan: dict[str, Any], trusted_points, legacy_main) -> dict[str, Any]:
    waypoints = plan.get("waypoints") or []
    if not 2 <= len(waypoints) <= 30:
        raise RuntimeError("Le plan final ne contient pas un nombre valide de waypoints.")
    coords = []
    for point in waypoints:
        lat, lon = float(point["lat"]), float(point["lon"])
        if not _trusted(trusted_points, lat, lon):
            raise RuntimeError(f"Le waypoint « {point.get('name','?')} » n'est pas géographiquement vérifié.")
        coords.append([lat, lon])

    result = ors.get_route(coords, legacy_main.distance_gps)
    route_coords = result.get("coords") or coords
    elevation = legacy_main.elevation_gain(route_coords)
    plan["route_preview"] = {
        "coords": _downsample(route_coords),
        "distance_km": float(result.get("distance") or legacy_main.distance_gps(route_coords)),
        "elevation_gain_m": int(elevation or 0),
        "fallback": bool(result.get("fallback")),
        "warning": result.get("warning"),
    }
    plan["model"] = OPENAI_MODEL
    return plan


def _run_agent(data: AIPlanRequest, legacy_main) -> dict[str, Any]:
    if OpenAI is None:
        raise HTTPException(status_code=503, detail="Le module OpenAI n'est pas installé sur le serveur.")
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="TrekMap AI n'est pas encore configurée : ajoute OPENAI_API_KEY dans les variables Render.",
        )

    client = OpenAI(api_key=OPENAI_API_KEY, timeout=AI_TIMEOUT_SECONDS)
    trusted_points: list[tuple[float, float]] = []
    input_items: list[Any] = [{"role": "user", "content": _build_user_prompt(data)}]

    for _round in range(AI_MAX_TOOL_ROUNDS):
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions=INSTRUCTIONS,
                tools=TOOLS,
                input=input_items,
                reasoning={"effort": "medium"},
                include=["web_search_call.action.sources"],
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Le moteur IA est temporairement indisponible ({exc.__class__.__name__}).") from exc

        input_items += list(response.output)
        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            continue

        for call in calls:
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if call.name == "finalize_trek_plan":
                try:
                    return _validate_and_enrich_plan(args, trusted_points, legacy_main)
                except Exception as exc:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
                        }
                    )
                    continue

            try:
                result = _execute_tool(call.name, args, trusted_points, legacy_main)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

    raise HTTPException(
        status_code=502,
        detail="L'IA n'a pas réussi à produire un itinéraire suffisamment vérifié. Essaie une région ou des contraintes plus précises.",
    )


def install_ai_planner(app, legacy_main):
    """Install TrekMap AI endpoints onto the existing FastAPI application."""

    @app.get("/ai/status")
    def ai_status():
        return {
            "configured": bool(OPENAI_API_KEY and OpenAI is not None),
            "model": OPENAI_MODEL,
            "web_search": True,
            "routing": bool(os.getenv("ORS_API_KEY", "").strip()),
        }

    @app.post("/ai/plan")
    def ai_plan(data: AIPlanRequest, user=Depends(legacy_main.current_user)):
        _rate_limit(int(user["id"]))
        return _run_agent(data, legacy_main)
