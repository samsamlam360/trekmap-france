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

Installer les dépendances : `python -m pip install -r requirements.txt`.

Définir en **local** `TREKMAP_ENV=development`, `FRONTEND_ORIGINS`, une `DATABASE_URL` de **test** et, si nécessaire, une clé ORS personnelle. Ne pas utiliser la base `production` pour les développements. Démarrer : `python -m uvicorn backend.app_v5:app --reload`.

Contrôles principaux :
- `python scripts/test_trekbrain_v9.py`
- `python scripts/test_trekbrain_v9_route_logistics.py`
- `python scripts/test_render_neon_contract.py`
- `node scripts/test_trekbrain_map_workspace.mjs`
- `node scripts/test_trekbrain_gpx_export.mjs`

Ne pas confondre tests simulés et treks réels : les benchmarks de production doivent signaler tous les échecs et préserver les artefacts des résultats.

## Exploitation

Lire [le guide de sécurité Neon et de migration](docs/TREKMAP_RUNBOOK_NEON.md) avant toute opération sur les branches, restaurations, bases de données ou Render. Des snapshots Neon sont utiles pour une restauration rapide, mais **ne remplacent pas un export PostgreSQL indépendant et protégé**.

Ne pas modifier/supprimer la base de production ni fusionner une régression non résolue pour faire passer la CI. Les API externes gratuites conservent des quotas et des délais variables ; aucune disponibilité illimitée n'est garantie.
