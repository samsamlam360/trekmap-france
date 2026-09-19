"""TrekMap Planner v6 language pack.

Extends v5 without duplicating the route engine: richer everyday French, common
typos/conjugations and better forcing of dated events through their host village.
"""
from __future__ import annotations

from . import compound_language_v5 as compound
from . import language_engine as language
from . import smart_planner_v5 as v5

PLANNER_VERSION = "trekmap-language-planner-v6"
v5.PLANNER_VERSION = PLANNER_VERSION

# Everyday French + common typing mistakes. Values remain in the planner's
# canonical vocabulary so the deterministic intent parser can consume them.
language.PHRASE_LEXICON.update({
    "chato": "chateau patrimoine",
    "chateu": "chateau patrimoine",
    "chateau a visiter": "visiter chateau patrimoine",
    "un truc historique": "patrimoine historique monument",
    "un endroit historique": "patrimoine historique",
    "un joli bled": "village typique",
    "un petit bled": "village typique",
    "bled": "village",
    "villlage": "village",
    "vilage": "village",
    "village sympa": "village typique",
    "fete de village": "fete village evenement local",
    "fete locale": "fete village evenement local",
    "festivale": "festival evenement local",
    "festoch": "festival evenement local",
    "festoche": "festival evenement local",
    "vide grenier": "brocante evenement local",
    "vide-grenier": "brocante evenement local",
    "kermesse": "fete evenement local",
    "marche nocturne": "marche nocturne evenement local",
    "animation locale": "evenement local",
    "faire un crochet": "faire un detour par",
    "faire un petit crochet": "faire un detour par",
    "faire un detour": "faire un detour par",
    "au passage": "si possible passer par",
    "tant qu on y est": "si possible",
    "tant qu'on y est": "si possible",
    "ca serait cool": "si possible",
    "ça serait cool": "si possible",
    "je m en fiche du denivele": "difficile sportif denivele libre",
    "pas envie de trop marcher": "facile max 14 km par jour",
    "pas trop long": "max 16 km par jour",
    "une grosse journee": "sportif 25 km par jour",
    "julliet": "juillet",
    "juilet": "juillet",
    "juiillet": "juillet",
    "septenbre": "septembre",
    "octobe": "octobre",
    "decenbre": "decembre",
})

language.TYPO_VOCAB.update({
    "chateau", "visiter", "visite", "passer", "passe", "village", "fete", "fetes",
    "festival", "brocante", "concert", "marche", "juillet", "septembre", "octobre",
    "decembre", "monument", "historique", "detour", "journee", "evenement", "local",
    "restaurant", "specialite", "dormir", "manger", "assister", "decouvrir",
})

# Conjugations and colloquial actions that the v5 clause extractor should accept.
compound.ACTION_WORDS = tuple(dict.fromkeys(compound.ACTION_WORDS + (
    "passe par", "passons par", "qu on passe", "qu'on passe", "visite", "visites",
    "qu on visite", "qu'on visite", "voir un", "aller voir", "j aimerais", "j'aimerai",
    "j aimerai", "je voudrais", "je veux", "on pourrait", "on peut", "faire escale",
    "faire une pause", "profiter pour", "assister a", "assister à",
)))

compound.SIDE_CATEGORIES["event"] = tuple(dict.fromkeys(compound.SIDE_CATEGORIES["event"] + (
    "fete locale", "fete de village", "evenement", "animation", "vide grenier", "kermesse",
)))
compound.SIDE_CATEGORIES["castle"] = tuple(dict.fromkeys(compound.SIDE_CATEGORIES["castle"] + (
    "chateau fort", "site fortifie", "donjon",
)))


def _candidate_prompts(normalized: str, targets: list[dict], request_structure: dict) -> list[str]:
    semantic = " ".join(
        v5.CATEGORY_TERMS.get(req.get("kind"), "")
        for req in request_structure.get("side_requests") or []
    )
    base = (normalized + " " + semantic).strip()
    ranked = sorted(
        targets,
        key=lambda t: (
            0 if (t.get("request") or {}).get("target_date") else 1,
            0 if (t.get("request") or {}).get("required") else 1,
            0 if (t.get("request") or {}).get("preferred_day") else 1,
        ),
    )
    prompts = [base]
    for target in ranked[:2]:
        # Event titles are often not geocodable. A nearby host village is much
        # more robust and still forces the route through the event area.
        forced_name = target.get("village_name") or target.get("name")
        if forced_name:
            prompts.append(base + f" ; passer par {forced_name}")
    return list(dict.fromkeys(prompts))[:3]


v5._candidate_prompts = _candidate_prompts
install_smart_planner = v5.install_smart_planner
