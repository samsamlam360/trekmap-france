"""Display-only water resources for TrekBrain v9.

Water points are useful map information, but they must not bend the calculated
hiking line and their absence must not make an otherwise valid trek impossible.
The walking route is decided by paths, overnight stops and explicit user
waypoints. Water is attached afterwards as nearby map context.
"""
from __future__ import annotations

_INSTALLED = False


def install_water_display_only(v3, resources) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_route_points = v3._route_points_for_candidate
    original_report = resources.route_safety_report
    original_enrich = resources.enrich_resources

    def route_points_for_candidate(candidate, all_items, intent, forced_via):
        # Future-proof the invariant even if v3's scenic categories change:
        # a drinking-water POI can never become an ORS waypoint by accident.
        routing_items = [
            item for item in (all_items or [])
            if not isinstance(item, dict) or item.get("category") != "water"
        ]
        return original_route_points(candidate, routing_items, intent, forced_via)

    def route_safety_report(result, request=None):
        report = dict(original_report(result, request))
        blockers = list(report.get("blockers") or [])
        warnings = list(report.get("warnings") or [])

        # Water availability is contextual information, not route feasibility.
        # Remove only the legacy water-specific safety blocker/warnings; all
        # geometry, campsite and walking-router safety checks remain untouched.
        water_blockers = [
            text for text in blockers
            if "information d'eau exploitable" in str(text).casefold()
            or "information d eau exploitable" in str(text).casefold()
        ]
        blockers = [text for text in blockers if text not in water_blockers]
        warnings = [
            text for text in warnings
            if "information d'eau insuffisante" not in str(text).casefold()
            and "information d eau insuffisante" not in str(text).casefold()
        ]
        if request is not None and getattr(request, "require_water", False):
            warnings.append(
                "Points d'eau affichés à titre informatif près du tracé ; ils ne sont pas imposés comme passages du parcours et leur disponibilité/potabilité doit être vérifiée."
            )
        report["blockers"] = blockers
        report["warnings"] = list(dict.fromkeys(warnings))
        report["safe"] = not blockers
        report["water_routing_mode"] = "display-only"
        return report

    def enrich_resources(result):
        enriched = original_enrich(result)
        resources_map = enriched.setdefault("map_resources", {})
        resources_map["water_mode"] = "display-only"
        resources_map["water_note"] = (
            "Les points d'eau sont des repères cartographiques proches du tracé. "
            "TrekBrain ne détourne pas l'itinéraire pour passer dessus."
        )
        return enriched

    v3._route_points_for_candidate = route_points_for_candidate
    resources.route_safety_report = route_safety_report
    resources.enrich_resources = enrich_resources


__all__ = ["install_water_display_only"]
