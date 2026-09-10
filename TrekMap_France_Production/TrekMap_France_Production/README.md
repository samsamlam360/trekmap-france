# TrekMap France - préparation au déploiement

Cette version reprend la version fonctionnelle 4.5-secure et la prépare pour un déploiement Render.

## Structure

- `backend/main.py` : API FastAPI + service de l'interface web
- `backend/database.py` : connexion PostgreSQL/PostGIS
- `frontend/index.html` : interface TrekMap France
- `requirements.txt` : dépendances Python
- `render.yaml` : configuration Render

## Lancer en local

Depuis la racine du projet :

```powershell
$env:DATABASE_URL="postgresql+psycopg2://postgres:motdepasse@localhost:5432/trekmap"
$env:TREKMAP_ENV="development"
$env:FRONTEND_ORIGINS="http://127.0.0.1:5500,http://localhost:5500"
$env:ORS_API_KEY="TA_CLE_ORS"
python -m uvicorn backend.main:app --reload
```

L'interface est ensuite disponible sur `http://127.0.0.1:8000/`.

## Déploiement Render

1. Créer un dépôt GitHub et y envoyer le contenu de ce dossier.
2. Dans Render, créer un Blueprint depuis ce dépôt.
3. Le fichier `render.yaml` crée le service web et la base.
4. Renseigner les quatre secrets demandés : `ORS_API_KEY`, `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
5. Après le premier déploiement, activer PostGIS si nécessaire avec :

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

L'application exécute aussi cette commande au démarrage.

## Important pour la base gratuite

Le plan PostgreSQL gratuit est adapté au test, pas à une vraie mise en production durable. Render indique que les bases Postgres gratuites expirent après 30 jours. Pour un site public durable, passer la base à un plan payant et conserver des sauvegardes.

## Sécurité

Les secrets ne sont pas dans le code. En production, les sessions utilisent un cookie HttpOnly sécurisé et une protection CSRF. La documentation FastAPI est désactivée en production.

## ORS

La clé OpenRouteService doit être configurée uniquement comme variable d'environnement. Ne jamais la mettre dans GitHub ni dans `index.html`.
