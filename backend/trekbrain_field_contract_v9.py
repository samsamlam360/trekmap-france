"""Human-level field scenarios for TrekBrain v9 request understanding.

These cases deliberately exercise complete user requests rather than one backend
component at a time.  They are deterministic and network-free: geocoding is
stubbed by the test runner, while request reconciliation and intent parsing are
the same production functions used by TrekBrain.

A scenario only states measurable expectations.  It is not a route fixture and
does not freeze the planner's implementation.
"""
from __future__ import annotations

FIELD_SCENARIOS = [
    # Route shape and contradiction handling.
    {"id": "shape-loop", "prompt": "Je veux une boucle de 3 jours autour de Chartres.", "expect": {"route_type": "Boucle"}},
    {"id": "shape-circuit", "prompt": "Je veux un circuit de randonnée autour de Chartres sur 2 jours.", "expect": {"route_type": "Boucle"}},
    {"id": "shape-traverse", "prompt": "Je veux une traversée de 3 jours en Touraine.", "expect": {"route_type": "Traversée"}},
    {"id": "shape-not-loop", "prompt": "Je veux aller de Tours à Chinon en 3 jours. Ce n'est pas une boucle.", "expect": {"route_type": "Traversée"}},
    {"id": "shape-not-in-loop", "prompt": "Trek de 3 jours en Touraine, pas en boucle.", "expect": {"route_type": "Traversée"}},
    {"id": "shape-roundtrip", "prompt": "Je veux un aller-retour de randonnée sur 2 jours autour de Chartres.", "expect": {"route_type": "Aller-retour"}},
    {"id": "shape-linear", "prompt": "Je veux une itinérance linéaire sur 4 jours dans le Vercors.", "expect": {"route_type": "Traversée"}},
    {"id": "shape-point-to-point", "prompt": "Je veux un trek point à point sur 3 jours en Touraine.", "expect": {"route_type": "Traversée"}},
    {"id": "shape-start-finish", "prompt": "Départ de Tours et arrivée à Chinon, 3 jours de marche.", "expect": {"route_type": "Traversée", "start_query": "Tours", "end_query": "Chinon"}},
    {"id": "shape-generic-roaming", "prompt": "Je veux une itinérance de 3 jours dans le Vercors.", "expect": {"route_type": "Itinérance"}},

    # Duration, distance and elevation constraints.
    {"id": "days-five", "prompt": "Randonnée autour de Chartres en 5 jours, 18 km par jour.", "expect": {"days": 5}},
    {"id": "daily-18", "prompt": "Boucle autour de Chartres, 18 km par jour pendant 3 jours.", "expect": {"daily_target": 18.0}},
    {"id": "range-a", "prompt": "Boucle de 3 jours autour de Chartres, 15 à 20 km par jour.", "expect": {"daily_min": 15.0, "daily_max": 20.0, "daily_target": 17.5}},
    {"id": "range-dash", "prompt": "Boucle de 3 jours autour de Chartres, 14-18 km/jour.", "expect": {"daily_min": 14.0, "daily_max": 18.0, "daily_target": 16.0}},
    {"id": "range-between", "prompt": "Boucle de 3 jours autour de Chartres, entre 16 et 20 km par jour.", "expect": {"daily_min": 16.0, "daily_max": 20.0, "daily_target": 18.0}},
    {"id": "daily-max", "prompt": "Boucle de 3 jours autour de Chartres, maximum 17 km par jour.", "base": {"daily_km": 20}, "expect": {"daily_max": 17.0, "daily_target": 17.0}},
    {"id": "daily-min", "prompt": "Boucle de 3 jours autour de Chartres, au moins 16 km par jour.", "base": {"daily_km": 14}, "expect": {"daily_min": 16.0, "daily_target": 16.0}},
    {"id": "total-distance", "prompt": "Boucle autour de Chartres en 5 jours, 90 km au total.", "expect": {"days": 5, "daily_target": 18.0, "total_target": 90.0}},
    {"id": "dplus-limit", "prompt": "Boucle sportive de 3 jours dans le Vercors, maximum 800 m de dénivelé par jour.", "expect": {"max_dplus_day": 800}},
    {"id": "decimal-distance", "prompt": "Boucle de 3 jours autour de Chartres, 17,5 km par jour.", "expect": {"daily_target": 17.5}},

    # Difficulty, lodging, transit and resources.
    {"id": "difficulty-easy", "prompt": "Je veux une randonnée facile autour de Chartres sur 2 jours.", "expect": {"difficulty": "easy"}},
    {"id": "difficulty-not-hard", "prompt": "Je veux une randonnée pas difficile autour de Chartres sur 2 jours.", "expect": {"difficulty": "easy"}},
    {"id": "difficulty-hard", "prompt": "Je veux une randonnée sportive dans le Vercors sur 3 jours.", "expect": {"difficulty": "hard"}},
    {"id": "sleep-camping", "prompt": "Boucle de 3 jours autour de Chartres avec camping chaque soir.", "base": {"require_accommodation": False}, "expect": {"accommodation": "camping", "sleep": True}},
    {"id": "sleep-refuge", "prompt": "Randonnée de 3 jours dans le Vercors avec refuge ou gîte chaque soir.", "base": {"require_accommodation": False}, "expect": {"accommodation": "refuge", "sleep": True}},
    {"id": "sleep-bivouac", "prompt": "Randonnée de 3 jours dans le Vercors en bivouac.", "base": {"require_accommodation": False}, "expect": {"accommodation": "bivouac", "sleep": True}},
    {"id": "sleep-no-camping-refuge", "prompt": "Randonnée de 3 jours dans le Vercors, pas de camping, je préfère un refuge.", "expect": {"accommodation": "refuge"}},
    {"id": "transit-positive", "prompt": "Je veux une boucle autour de Chartres accessible en train depuis une gare.", "base": {"require_transit": False}, "expect": {"transit": True}},
    {"id": "transit-negative", "prompt": "Je viens en voiture uniquement, sans train ni bus.", "base": {"require_transit": True}, "expect": {"transit": False}},
    {"id": "water-positive", "prompt": "Boucle de 3 jours autour de Chartres avec des points d'eau potable.", "base": {"require_water": False}, "expect": {"water": True}},
    {"id": "water-negative", "prompt": "Boucle de 2 jours autour de Chartres, pas besoin de points d'eau.", "base": {"require_water": True}, "expect": {"water": False}},
    {"id": "food-positive", "prompt": "Boucle de 3 jours autour de Chartres avec ravitaillement et boulangerie.", "base": {"require_food": False}, "expect": {"food": True}},
    {"id": "food-negative", "prompt": "Boucle de 2 jours autour de Chartres sans ravitaillement.", "base": {"require_food": True}, "expect": {"food": False}},
    {"id": "sleep-positive", "prompt": "Boucle de 3 jours autour de Chartres avec hébergement chaque soir.", "base": {"require_accommodation": False}, "expect": {"sleep": True}},
    {"id": "sleep-negative", "prompt": "Boucle de 2 jours autour de Chartres sans hébergement.", "base": {"require_accommodation": True}, "expect": {"sleep": False}},

    # Geographic reconciliation and stale-form protection.
    {"id": "geo-belle-ile", "prompt": "Je veux faire le tour de Belle-Île-en-Mer en 5 jours.", "base": {"region": "Bretagne", "route_type": "Traversée"}, "resolved": {"region": "Belle-Île-en-Mer", "route_type": "Boucle"}, "meta": {"island_access_mode": "transport-then-hike", "preferred_trail": "GR 340"}},
    {"id": "geo-mont-saint-michel", "prompt": "Je veux une randonnée autour du Mont Saint-Michel en 4 jours.", "base": {"region": "Bretagne"}, "resolved": {"region": "Mont Saint-Michel", "route_type": "Boucle"}},
    {"id": "geo-chartres-form-kept", "prompt": "Je veux une boucle de 3 jours autour de Chartres.", "base": {"region": "Chartres"}, "resolved": {"region": "Chartres", "route_type": "Boucle"}, "meta": {"region_overridden": False}},
    {"id": "geo-after-trip-visit", "prompt": "Randonnée autour de Chartres en 2 jours. Après le trek, visiter Paris.", "base": {"region": "Chartres"}, "resolved": {"region": "Chartres"}, "meta": {"forced_waypoint": None}},
    {"id": "geo-stale-region-conflict", "prompt": "Je veux visiter Chinon pendant la randonnée.", "base": {"region": "Chartres"}, "resolved": {"region": "Chinon"}, "meta": {"region_overridden": True}},
]

FIELD_SCENARIO_COUNT = len(FIELD_SCENARIOS)
assert FIELD_SCENARIO_COUNT == 40

__all__ = ["FIELD_SCENARIOS", "FIELD_SCENARIO_COUNT"]
