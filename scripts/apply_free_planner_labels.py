from pathlib import Path

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("L'interface de planification doit être injectée avant les libellés du conseiller.")

replacements = {
    "TrekMap AI": "Conseiller TrekMap",
    "Trek IA": "Conseiller",
    "<span>IA</span>": "<span>Conseil</span>",
    "L'IA recherche les lieux, vérifie la logistique et fait calculer le vrai tracé.": "Le moteur comprend tes contraintes, compare plusieurs scénarios et calcule le meilleur tracé trouvé.",
    "L'IA vérifiera d'abord les données utiles plutôt que d'inventer une ligne sur une carte.": "Le conseiller interprète ta demande, compare plusieurs parcours et s'appuie sur des lieux cartographiés réels.",
    "TrekMap AI aide à préparer.": "Le conseiller TrekMap aide à préparer.",
    "Modifier avec l'IA": "Demander une modification",
    "La préparation IA a échoué.": "La préparation du trek a échoué.",
    "Aperçu IA indisponible": "Aperçu du plan indisponible",
    "Trek IA enregistré en privé.": "Trek conseillé enregistré en privé.",
    "Trek IA'": "Trek conseillé'",
    "Connecte-toi pour utiliser TrekMap AI.": "Connecte-toi pour utiliser le conseiller TrekMap.",
}
for old, new in replacements.items():
    html = html.replace(old, new)

html = html.replace(
    "<div class=\"tm-ai-note\">Le conseiller TrekMap aide à préparer.",
    "<div class=\"tm-ai-note\"><b>0 € par requête côté moteur.</b> Le conseiller TrekMap analyse les contraintes de randonnée, compare plusieurs scénarios et utilise des données cartographiques publiques. ",
)

html = html.replace(
    "const steps=['Analyse de ta demande…','Recherche de lieux réels…','Vérification des points d’eau et nuitées…','Recherche des accès train et bus…','Calcul du tracé pédestre…','Vérification des étapes et des sources…'];",
    "const steps=['Interprétation de ta demande…','Recherche des lieux pertinents…','Création de plusieurs scénarios…','Comparaison distance, paysages et logistique…','Calcul des meilleurs tracés pédestres…','Choix du trek le plus cohérent…'];",
)

html = html.replace(
    "const limitations=p.confidence?.limitations||[];",
    "const limitations=p.confidence?.limitations||[],advisor=Array.isArray(p.advisor_notes)?p.advisor_notes:[],understood=String(p.understood_request||'');",
)

needle = "      <div class=\"tm-ai-badges\"><span class=\"tm-ai-badge\">${esc(p.region||'France')}</span><span class=\"tm-ai-badge\">${esc(difficultyLabel[p.difficulty]||p.difficulty||'Moyen')}</span><span class=\"tm-ai-badge\">${esc(p.route_type||'Trek')}</span><span class=\"tm-ai-badge\">${esc(p.best_season||'Saison à vérifier')}</span></div>\n      <div class=\"tm-ai-stats\">"
replacement = "      <div class=\"tm-ai-badges\"><span class=\"tm-ai-badge\">${esc(p.region||'France')}</span><span class=\"tm-ai-badge\">${esc(difficultyLabel[p.difficulty]||p.difficulty||'Moyen')}</span><span class=\"tm-ai-badge\">${esc(p.route_type||'Trek')}</span><span class=\"tm-ai-badge\">${esc(p.best_season||'Saison à vérifier')}</span></div>\n      ${understood?`<section class=\"tm-ai-section tm-ai-advisor\"><h3>🧠 Ce que j’ai compris</h3><div class=\"tm-ai-advisor-understood\">${esc(understood)}</div></section>`:''}\n      ${advisor.length?`<section class=\"tm-ai-section tm-ai-advisor\"><h3>💡 Pourquoi je te conseille ce trek</h3><div class=\"tm-ai-list\">${advisor.map((x,i)=>`<div class=\"tm-ai-item\"><b>${i+1}.</b> ${esc(x)}</div>`).join('')}</div></section>`:''}\n      <div class=\"tm-ai-stats\">"
if needle not in html:
    raise SystemExit("Le bloc résultats du conseiller a changé : impossible d'injecter les explications.")
html = html.replace(needle, replacement, 1)

extra_css = '''
<style id="trekmap-smart-advisor-css">
.tm-ai-advisor{padding:11px;border:1px solid #cfe4d8;border-radius:14px;background:linear-gradient(145deg,#f5fbf8,#edf7f2)}
.tm-ai-advisor h3{color:#176447!important}.tm-ai-advisor-understood{font-size:11px;line-height:1.55;color:#46665a;font-weight:700}
.tm-ai-advisor .tm-ai-item{background:rgba(255,255,255,.8)}
</style>
'''
html = html.replace("</body>", extra_css + "\n</body>", 1)

html_path.write_text(html, encoding="utf-8")
print("TrekMap smart planner labels and advisor UI applied")
