"""Extended production benchmark for TrekBrain v9.

This suite deliberately complements, rather than replaces, the six stable
reference treks. It exercises different French terrain, resource densities and
request shapes so regressions outside the core benchmark are visible without
making every deployment depend on these exploratory cases.
"""
from __future__ import annotations

import os

import benchmark_trekbrain_v9_production as core


EXTENDED_SCENARIOS = [
    {
        "id": "gavarnie-pyrenees-refuge-loop",
        "prompt": (
            "Je veux une boucle de randonnée sportive de 2 jours autour de Gavarnie dans les Pyrénées, "
            "environ 14 km par jour, avec un refuge ou un gîte pour dormir et des points d'eau. "
            "Je veux rester sur de vrais chemins pédestres et éviter les détours artificiels."
        ),
        "region": "Gavarnie, Hautes-Pyrénées",
        "days": 2,
        "daily_km": 14,
        "difficulty": "hard",
        "route_type": "Boucle",
        "require_transit": False,
        "require_water": True,
        "require_accommodation": True,
        "require_food": False,
        "expect_type": "boucle",
        "expect_close": True,
    },
    {
        "id": "hohneck-vosges-refuge-loop",
        "prompt": (
            "Je veux une boucle de 2 jours autour du Hohneck dans les Vosges, environ 16 km par jour, "
            "avec refuge ou auberge pour la nuit et des points d'eau. Je veux privilégier les sentiers."
        ),
        "region": "Hohneck, Vosges",
        "days": 2,
        "daily_km": 16,
        "difficulty": "hard",
        "route_type": "Boucle",
        "require_transit": False,
        "require_water": True,
        "require_accommodation": True,
        "require_food": False,
        "expect_type": "boucle",
        "expect_close": True,
    },
    {
        "id": "crozon-coastal-camping-loop",
        "prompt": (
            "Je veux une boucle de randonnée de 3 jours sur la presqu'île de Crozon, environ 18 km par jour, "
            "avec camping chaque soir, eau et ravitaillement. Je veux rester au maximum sur des sentiers côtiers "
            "et éviter les longues portions routières."
        ),
        "region": "Presqu'île de Crozon",
        "days": 3,
        "daily_km": 18,
        "difficulty": "medium",
        "route_type": "Boucle",
        "require_transit": False,
        "require_water": True,
        "require_accommodation": True,
        "require_food": True,
        "expect_type": "boucle",
        "expect_close": True,
    },
    {
        "id": "mont-lozere-cevennes-loop",
        "prompt": (
            "Je veux une boucle de 3 jours autour du mont Lozère dans les Cévennes, environ 16 km par jour, "
            "avec une solution pour dormir chaque soir, des points d'eau et du ravitaillement quand c'est possible. "
            "Je veux des sentiers de randonnée réalistes."
        ),
        "region": "Mont Lozère, Cévennes",
        "days": 3,
        "daily_km": 16,
        "difficulty": "medium",
        "route_type": "Boucle",
        "require_transit": False,
        "require_water": True,
        "require_accommodation": True,
        "require_food": True,
        "expect_type": "boucle",
        "expect_close": True,
    },
    {
        "id": "fontainebleau-accessible-loop",
        "prompt": (
            "Je veux une boucle facile de 2 jours dans la forêt de Fontainebleau, environ 18 km par jour, "
            "avec un hébergement simple, de l'eau, du ravitaillement et un accès utile en transport en commun. "
            "Je veux de vrais chemins forestiers."
        ),
        "region": "Forêt de Fontainebleau",
        "days": 2,
        "daily_km": 18,
        "difficulty": "easy",
        "route_type": "Boucle",
        "require_transit": True,
        "require_water": True,
        "require_accommodation": True,
        "require_food": True,
        "expect_type": "boucle",
        "expect_close": True,
    },
    {
        "id": "dijon-beaune-traverse",
        "prompt": (
            "Je veux aller de Dijon à Beaune à pied en 3 jours, environ 16 km par jour. Ce n'est pas une boucle. "
            "Je veux des chemins praticables, une solution pour dormir chaque soir, de l'eau, du ravitaillement "
            "et des transports utiles au départ et à l'arrivée."
        ),
        "region": "Dijon",
        "days": 3,
        "daily_km": 16,
        "difficulty": "medium",
        "route_type": "Traversée",
        "require_transit": True,
        "require_water": True,
        "require_accommodation": True,
        "require_food": True,
        "expect_type": "traversee",
        "expect_close": False,
    },
]


def main() -> None:
    core.SCENARIOS = EXTENDED_SCENARIOS
    core.OUT_DIR = core.Path(
        os.getenv("TREKBRAIN_BENCHMARK_OUT", "benchmark-results-extended")
    )
    core.OUT_DIR.mkdir(parents=True, exist_ok=True)
    core.main()


if __name__ == "__main__":
    main()
