"""Grounded, no-LLM questions about the displayed itinerary.

This is a specialist data interpreter, not a general conversational model.
Client-supplied context is never treated as externally verified evidence.
"""
import re
import unicodedata
from typing import Annotated

from pydantic import BaseModel, Field, ConfigDict


class Stage(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    distance_km: float | None = Field(default=None, ge=0, le=10000)
    overnight: str = Field(default="", max_length=2000)
    water_notes: str = Field(default="", max_length=2000)


class Transport(BaseModel):
    outbound: str = Field(default="", max_length=2000)
    return_: str = Field(default="", alias="return", max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=800)
    stages: list[Stage] = Field(default_factory=list, max_length=21)
    transport: Transport = Field(default_factory=Transport)
    limitations: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=12)


def answer(data: AskRequest) -> dict:
    text = "".join(c for c in unicodedata.normalize("NFD", data.question.casefold()) if unicodedata.category(c) != "Mn")
    selected = list(enumerate(data.stages, 1))
    day = re.search(r"\b(?:jour|etape|journee)\s*(\d{1,2})\b", text)
    if day:
        selected = [(i, stage) for i, stage in selected if i == int(day[1])]
        if not selected:
            return {"answer": "Cette étape n'existe pas dans le parcours affiché.", "mode": "local-data", "verified_live": False}
    topics = []
    lines = []
    if re.search(r"\b(eau|boire|potable|fontaine|source)\b", text):
        topics.append("eau")
        lines += [f"Jour {i} : {s.water_notes or 'aucune donnée sur l’eau.'}" for i, s in selected]
        lines.append("Une mention dans la carte ne confirme ni le débit ni la potabilité actuelle. Vérifie ces points avant de partir.")
    if re.search(r"\b(dormir|nuit|nuits|nuitee|nuitees|camping|refuge|hebergement|bivouac)\b", text):
        topics.append("nuitées")
        lines += [f"Jour {i} : {s.overnight or 'aucune solution renseignée.'}" for i, s in selected if i < len(data.stages)]
        lines.append("Un hébergement mentionné n'est pas une réservation. Ouverture, places et autorisations restent à vérifier.")
    if re.search(r"\b(train|bus|gare|transport|transports|retour|aller|horaire|horaires)\b", text):
        topics.append("transports")
        lines += ["Aller : " + (data.transport.outbound or "non renseigné."),
                  "Retour : " + (data.transport.return_ or "non renseigné."),
                  "La proximité d'un arrêt ne garantit pas une desserte. Aucun horaire en temps réel n'a été vérifié ici."]
    if re.search(r"\b(km|distance|distances|long|longue|longues|etape|etapes|difficulte|difficile|fatigue)\b", text):
        topics.append("étapes")
        lines += [f"Jour {i} : {s.distance_km:g} km." if s.distance_km is not None else f"Jour {i} : distance inconnue." for i, s in selected]
        if selected and all(s.distance_km is not None for _, s in selected):
            lines.append(f"Total de ces étapes : {sum(s.distance_km for _, s in selected):g} km.")
        lines.append("La distance seule ne décrit pas la difficulté : dénivelé, terrain et conditions doivent aussi être pris en compte.")
    if re.search(r"\b(limite|limites|fiable|fiabilite|pourquoi|verifier|risque|sur|securite)\b", text):
        topics.append("limites")
        lines += [str(x)[:1000] for x in data.limitations[:8]]
        lines.append("Le score est un contrôle de cohérence, pas une garantie de sécurité. Météo, fermetures et conditions du terrain ne sont pas vérifiées par ce dialogue.")
    if not topics:
        lines = ["Je peux expliquer les étapes, l'eau, les nuitées, les transports et les limites du trek affiché. Exemple : « Où trouver de l'eau au jour 2 ? » Pour changer le parcours, utilise la demande de modification du plan. Ce mode local n'est pas un assistant généraliste."]
    if not data.stages:
        lines.insert(0, "Aucune étape n'a été transmise : commence par générer un parcours.")
    return {"answer": "\n\n".join(lines), "topics": topics, "mode": "local-data", "verified_live": False,
            "context": "Données du parcours affiché, sans nouvelle recherche ni recalcul."}
