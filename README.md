# TrekMap France

Application web de randonnée avec FastAPI, PostgreSQL/PostGIS (Neon) et TrekBrain v9.

## Production (octobre 2026)

- Site : https://trekmap-france.onrender.com
- Dépôt : `samsamlam360/trekmap-france`, branche `main`
- Hébergement : service web Python Render `trekmap-france`, plan `free`.
- Point d'entrée **effectif** : `backend.app_v5:app`.
- Données : PostgreSQL 17/PostGIS sur Neon, projet `trekmap-france`, branche `production`.
- `DATABASE_URL` est un secret du service Render. Ne jamais le committer ni afficher son mot de passe.
- L'ancienne base Render `trekmap-france-db` a expiré et est suspendue. **Ne pas la recréer ni la supprimer pendant la migration.**
- TrekBrain : `TREKBRAIN_VERSION=v9`, `TREKBRAIN_RELEASE_CHANNEL=v9-stable`, `TREKBRAIN_FREE_MODE=1`.

Le fichier `render.yaml` ne déclare **aucune** nouvelle base Render. La configuration du service conserve un secret `DATABASE_URL` indépendant du dépôt et `DB_SSLMODE=require`.

## Structure

- `backend/app_v5.py` : application ASGI de production.
- `backend/database.py` : accès PostgreSQL/PostGIS.
- `backend/trekbrain_pipeline_core_v9.py` : orchestration TrekBrain v9.
- `frontend/index.html` et `scripts/apply_*.py` : interface et assemblage Render.
- `scripts/render_preflight.py` : régressions hors ligne, contrôle d'environnement et import de l'application.
- `.github/workflows/` : tests, santé, benchmarks en production.

## Développer et vérifier

Les verdicts de préparation, preuves par journée et contrôles à froid sont décrits dans [le contrat de préparation](docs/TREKBRAIN_PREPARATION.md).

Installer les dépendances : `python -m pip install -r requirements.txt`.

Définir en **local** `TREKMAP_ENV=development`, `FRONTEND_ORIGINS`, une `DATABASE_URL` de **test** et, si nécessaire, une clé ORS personnelle. Ne pas utiliser la base `production` pour les développements. Démarrer : `python -m uvicorn backend.app_v5:app --reload`.

Contrôles principaux :
- `python scripts/test_trekbrain_v9.py`
- `python scripts/test_trekbrain_v9_route_logistics.py`
- `python scripts/test_render_neon_contract.py`
- `node scripts/test_trekbrain_map_workspace.mjs`
- `node scripts/test_trekbrain_gpx_export.mjs`

Ne pas confondre tests simulés et treks réels : les benchmarks de production doivent signaler tous les échecs et préserver les artefacts des résultats.

## Benchmarks et coût des fournisseurs

Les gros benchmarks réseau ne doivent pas être exécutés par Render au moment de construire ou redéployer le site. `TREKBRAIN_RUN_BENCHMARK=0` est imposé dans le blueprint et doit également être désactivé dans les variables du service existant. Les tests hors réseau restent requis avant chaque déploiement ; les tests réels sur de nouvelles régions se lancent dans les workflows GitHub séparés, avec limites de fréquence et de volume. Ne jamais lancer une vague de requêtes ORS/Overpass à chaque push.

La suite `trekbrain-production-suite.yml` exécute **47 scénarios en série** : trois passes de six treks historiques, neuf treks étendus puis vingt régions. Elle se lance manuellement ou chaque lundi à 03:17 UTC, après vérification du commit réellement déployé. Les audits isolés de production sont manuels ; aucun de ces gros benchmarks ne se déclenche sur un push. Une passe refusée ou incomplète n'empêche pas les suivantes de s'exécuter. Le bilan final échoue si une suite a échoué ou n'a pas été exécutée, et les rapports JSON/Markdown sont conservés en artefacts.

Les rapports séparent `structure_ok` (tracé exploitable), `preparation_ok` (besoins obligatoires confirmés) et `ok` (les deux). Un score élevé ou un tracé valide ne suffisent pas pour annoncer « prêt à partir » : l'eau, le ravitaillement, les nuitées, les accès demandés et les limites de distance sont évalués. Les nuitées à pied, les transferts et les nuits non résolues restent visibles séparément.

L'audit `trekbrain-cold-benchmark.yml` est **manuel uniquement** et exige une clé ORS existante dans le secret GitHub `ORS_API_KEY`. Il vérifie la configuration avant d'appeler un fournisseur ; une clé absente produit une erreur de configuration, sans faux succès. Ses quatre cas se lancent chacun dans un processus neuf, avec cache OSM persistant désactivé et base isolée ; les caches propres aux fournisseurs ne sont pas contrôlés. Chaque cas est limité à 90 secondes, la suite à 400 secondes, avec au moins 20 secondes entre débuts de cas. Aucun secret de production n'est copié et aucune clé ou infrastructure payante n'est créée par cet audit.

## Exploitation

Lire [le guide de sécurité Neon et de migration](docs/TREKMAP_RUNBOOK_NEON.md) avant toute opération sur les branches, restaurations, bases de données ou Render. Des snapshots Neon sont utiles pour une restauration rapide, mais **ne remplacent pas un export PostgreSQL indépendant et protégé**.

Ne pas modifier/supprimer la base de production ni fusionner une régression non résolue pour faire passer la CI. Les API externes gratuites conservent des quotas et des délais variables ; aucune disponibilité illimitée n'est garantie.
