"""OpenRouteService client for TrekMap France."""

import os
from typing import Any

import requests

ORS_API_KEY = os.getenv("ORS_API_KEY", "").strip()
ORS_URL = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/geojson"


def _fallback(coords, distance_gps):
    return {
        "coords": coords,
        "distance": distance_gps(coords),
        "fallback": True,
    }


def get_route(coords, distance_gps):
    """Ask ORS for a walking route, with a safe local fallback and clear diagnostics."""
    fallback = _fallback(coords, distance_gps)

    if not ORS_API_KEY:
        return {
            **fallback,
            "warning": "OpenRouteService non configuré : ORS_API_KEY est absente du serveur Render.",
        }

    if len(coords) > 50:
        return {
            **fallback,
            "warning": "OpenRouteService : maximum de 50 points pour ce tracé.",
        }

    try:
        payload = {
            "coordinates": [[float(p[1]), float(p[0])] for p in coords],
            "instructions": False,
        }
        response = requests.post(
            ORS_URL,
            json=payload,
            headers={
                "Authorization": ORS_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=25,
        )

        if response.status_code in (401, 403):
            return {
                **fallback,
                "warning": f"OpenRouteService : clé API refusée (HTTP {response.status_code}). Vérifie ORS_API_KEY dans Render.",
            }
        if response.status_code == 429:
            return {
                **fallback,
                "warning": "OpenRouteService : limite de requêtes atteinte (HTTP 429).",
            }
        if response.status_code >= 500:
            return {
                **fallback,
                "warning": f"OpenRouteService indisponible temporairement (HTTP {response.status_code}).",
            }
        if not response.ok:
            return {
                **fallback,
                "warning": f"OpenRouteService a répondu HTTP {response.status_code}.",
            }

        data: dict[str, Any] = response.json()
        feature = (data.get("features") or [None])[0]
        if not feature:
            return {**fallback, "warning": "OpenRouteService n'a renvoyé aucun tracé."}

        geometry = feature.get("geometry", {}).get("coordinates", [])
        summary = feature.get("properties", {}).get("summary", {})
        route = [[float(p[1]), float(p[0])] for p in geometry if len(p) >= 2]

        if len(route) < 2 or "distance" not in summary:
            return {**fallback, "warning": "Réponse OpenRouteService invalide : tracé direct conservé."}

        return {
            "coords": route,
            "distance": round(float(summary["distance"]) / 1000, 2),
            "fallback": False,
        }

    except requests.Timeout:
        return {**fallback, "warning": "OpenRouteService : délai d'attente dépassé."}
    except requests.RequestException as exc:
        return {
            **fallback,
            "warning": f"OpenRouteService inaccessible ({exc.__class__.__name__}) : tracé direct utilisé.",
        }
    except ValueError:
        return {**fallback, "warning": "OpenRouteService a renvoyé une réponse JSON invalide."}
    except Exception:
        return {**fallback, "warning": "Erreur inattendue avec OpenRouteService : tracé direct utilisé."}
