from pathlib import Path

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("L'interface de planification doit être injectée avant les libellés gratuits.")

replacements = {
    "TrekMap AI": "TrekMap Planner",
    "Trek IA": "Planificateur",
    "<span>IA</span>": "<span>Plan</span>",
    "L'IA recherche les lieux, vérifie la logistique et fait calculer le vrai tracé.": "Le planificateur recherche les lieux, vérifie la logistique et fait calculer le vrai tracé.",
    "L'IA vérifiera d'abord les données utiles plutôt que d'inventer une ligne sur une carte.": "Le planificateur vérifiera d'abord les données utiles plutôt que d'inventer une ligne sur une carte.",
    "TrekMap AI aide à préparer.": "TrekMap Planner aide à préparer.",
    "Modifier avec l'IA": "Modifier le plan",
    "La préparation IA a échoué.": "La préparation a échoué.",
    "Aperçu IA indisponible": "Aperçu du plan indisponible",
    "Trek IA enregistré en privé.": "Trek planifié enregistré en privé.",
    "Trek IA'": "Trek planifié'",
}
for old, new in replacements.items():
    html = html.replace(old, new)

html = html.replace(
    "<div class=\"tm-ai-note\">TrekMap Planner aide à préparer.",
    "<div class=\"tm-ai-note\"><b>0 € par requête côté moteur.</b> TrekMap Planner utilise des règles locales et des données cartographiques publiques. ",
)

html_path.write_text(html, encoding="utf-8")
print("TrekMap free planner labels applied")
