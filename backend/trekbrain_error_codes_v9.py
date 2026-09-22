"""Stable, user-visible failure codes for TrekBrain v9.

The planner is a pipeline made of several external services and local validation
steps. A plain HTTP 500 does not tell us whether geocoding, Overpass, ORS Matrix,
ORS Directions, campsite selection or final safety validation failed. This module
turns the final human-readable error into a compact diagnostic object that can be
shown in the mobile UI and copied into a bug report.

No prompt text, account identifier or secret is stored in the diagnostic id.
"""
from __future__ import annotations

import re
import uuid
from typing import Any


def _text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail.strip()
    if isinstance(detail, dict):
        for key in ("message", "msg", "detail"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(detail or "").strip()


def _provider_status(message: str) -> int | None:
    match = re.search(r"\bHTTP\s*(\d{3})\b", message, flags=re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def classify_failure(detail: Any, *, api_status: int | None = None, preview: Any = None) -> dict[str, Any]:
    """Return a small deterministic diagnostic payload for a failed plan."""
    message = _text(detail)
    folded = message.casefold()
    provider_status = _provider_status(message)

    code = "TB-PLAN-UNKNOWN"
    stage = "planification"
    service = "TrekBrain"
    retryable = False
    next_check = "Vérifier le message complet et l’étape de planification indiquée."

    if "openrouteservice" in folded and "matrix" in folded:
        suffix = str(provider_status or "ERR")
        code = f"TB-ORS-MATRIX-{suffix}"
        stage = "équilibrage des étapes et nuitées"
        service = "OpenRouteService Matrix"
        retryable = provider_status is None or provider_status == 429 or provider_status >= 500
        next_check = "La matrice de distances pédestres a échoué. Vérifier ORS puis le secours Matrix/camping-first."
    elif "openrouteservice" in folded:
        if provider_status in {401, 403} or "clé api" in folded or "cle api" in folded:
            code = f"TB-ORS-AUTH-{provider_status or 'ERR'}"
            stage = "authentification du routeur"
            service = "OpenRouteService Directions"
            next_check = "Vérifier ORS_API_KEY sur Render et ses droits d’accès."
        elif provider_status == 429 or "limite de requêtes" in folded:
            code = "TB-ORS-DIR-429"
            stage = "routage pédestre"
            service = "OpenRouteService Directions"
            retryable = True
            next_check = "Le quota ou la limite ORS a été atteint. Vérifier le circuit breaker et réessayer plus tard."
        elif "délai" in folded or "delai" in folded or "timeout" in folded:
            code = "TB-ORS-DIR-TIMEOUT"
            stage = "routage pédestre"
            service = "OpenRouteService Directions"
            retryable = True
            next_check = "Le routeur a dépassé le délai. Vérifier la taille du candidat et le routage segmenté."
        else:
            suffix = str(provider_status or "ERR")
            code = f"TB-ORS-DIR-{suffix}"
            stage = "routage pédestre"
            service = "OpenRouteService Directions"
            retryable = provider_status is None or provider_status >= 500
            next_check = "Le calcul de géométrie pédestre a échoué. Vérifier le retry 5xx, le snap et le routage segmenté."
    elif "overpass" in folded or "openstreetmap" in folded:
        suffix = str(provider_status or "ERR")
        code = f"TB-OSM-OVERPASS-{suffix}"
        stage = "recherche des sentiers et ressources"
        service = "OpenStreetMap / Overpass"
        retryable = provider_status is None or provider_status == 429 or provider_status >= 500
        next_check = "Vérifier les serveurs Overpass, le rayon de recherche et le cache de découverte."
    elif any(word in folded for word in ("nominatim", "photon", "localiser la zone", "géocod", "geocod")):
        code = "TB-GEO-GEOCODE"
        stage = "localisation de la zone"
        service = "Géocodage"
        retryable = True
        next_check = "Vérifier la résolution du lieu et le garde des noms ambigus."
    elif "camping" in folded or "nuitée" in folded or "nuitee" in folded:
        code = "TB-PLAN-CAMPING"
        stage = "sélection des nuitées"
        service = "TrekBrain hébergements"
        next_check = "Vérifier les campings découverts, leur distance au corridor et l’équilibrage entre étapes."
    elif "km/jour" in folded or "distance quotidienne" in folded or "étape" in folded and "longue" in folded:
        code = "TB-PLAN-DISTANCE"
        stage = "équilibrage des journées"
        service = "TrekBrain contraintes"
        next_check = "Comparer les kilomètres de chaque étape avec la plage quotidienne réellement interprétée."
    elif any(word in folded for word in ("tracé pédestre n'est pas suffisamment validé", "tracé direct de secours", "saut géographique", "sécurité géographique")):
        code = "TB-SAFETY-ROUTE"
        stage = "validation finale du tracé"
        service = "TrekBrain sécurité géographique"
        next_check = "Inspecter la géométrie, le mode de routage et les bloqueurs du rapport de sécurité."
    elif "maximum recursion depth" in folded:
        code = "TB-INTERNAL-RECURSION"
        stage = "orchestration interne"
        service = "TrekBrain"
        next_check = "Inspecter la chaîne des wrappers v3/v5/v7/v9 pour une boucle d’appel."
    elif api_status and int(api_status) >= 500:
        code = f"TB-INTERNAL-{int(api_status)}"
        stage = "serveur TrekBrain"
        service = "TrekBrain API"
        retryable = True
        next_check = "Consulter les logs serveur correspondant à l’identifiant de diagnostic."
    elif api_status == 422:
        code = "TB-PLAN-422"
        stage = "validation de la demande"
        service = "TrekBrain"
        next_check = "Le moteur n’a pas validé de solution. Comparer l’interprétation de la demande et le dernier bloqueur."

    return {
        "version": 1,
        "id": uuid.uuid4().hex[:10].upper(),
        "code": code,
        "stage": stage,
        "service": service,
        "api_status": int(api_status) if api_status is not None else None,
        "provider_http_status": provider_status,
        "retryable": bool(retryable),
        "preview_available": bool(isinstance(preview, dict) and len(preview.get("coords") or []) >= 2),
        "next_check": next_check,
    }


__all__ = ["classify_failure"]
