# TrekMap France - déploiement

Version 4.5.1 préparée pour un déploiement Render propre.

## Structure

- `backend/main.py` : API FastAPI + logique principale
- `backend/main_production.py` : point d'entrée Render avec sécurité HTTP sans l'ancien contrôle CSRF bloquant
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

Le `render.yaml` utilise `backend.main_production:app`. Ce point d'entrée conserve l'application existante mais remplace l'ancien middleware CSRF par un contrôle d'origine et un limiteur de requêtes, afin d'éviter les refus d'authentification liés aux anciens cookies CSRF.

1. Connecter le dépôt GitHub à Render.
2. Créer ou synchroniser le Blueprint depuis `render.yaml`.
3. Renseigner les secrets : `ORS_API_KEY`, `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
4. Déployer la dernière version et vérifier le déploiement marqué **Live**.

## Base de données

PostgreSQL/PostGIS est configuré dans `render.yaml`. L'application crée l'extension PostGIS au démarrage si nécessaire.

Le plan PostgreSQL gratuit est adapté au test, pas à une mise en production durable. Pour un site public durable, utiliser une base adaptée et conserver des sauvegardes.

## Sécurité

Les secrets ne sont pas dans le code. Les sessions utilisent un cookie HttpOnly sécurisé en production. Les requêtes sont limitées sur les endpoints sensibles et les origines sont contrôlées en production. L'ancien contrôle CSRF qui provoquait `Protection CSRF : requête refusée.` n'est plus utilisé par l'entrée Render.

## ORS

La clé OpenRouteService doit être configurée uniquement comme variable d'environnement. Ne jamais la mettre dans GitHub ni dans `index.html`.
