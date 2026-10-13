# Procédure de production : Render + Neon

État vérifié le 13 octobre 2026. Cette procédure évite de casser un service fonctionnel sous prétexte de « nettoyer » sa migration.

## Inventaire vérifié

- Render : web service `trekmap-france` (`srv-dahd446743jc73cfje60`), workspace `My Workspace`, plan `free`, branche GitHub `main`.
- Render : ancienne PostgreSQL `trekmap-france-db`, expirée le 10 octobre 2026 et **suspendue**. Ne pas l'utiliser comme source de vérité ni la supprimer sans confirmation de fin de migration.
- Neon : projet `lingering-shadow-90188569`, base `trekmap`, branche de production `br-dry-darkness-argg1snk`, PostgreSQL 17/PostGIS, région Oregon.
- Connexion de production : `DATABASE_URL` secret Render, SSL requis ; ne jamais publier d'identifiants.
- Snapshot de sécurité manuel : `trekmap-pre-stabilisation-2026-10-13` (créé et vérifié par restauration isolée le 13 octobre). Le snapshot n'est **pas** une sauvegarde hors de Neon.
- À la vérification : 44 comptes, 12 treks, 2 photos en base. Ce sont des observations, pas des invariants à maintenir.

## Sauvegarde avant migration et indépendance

1. Identifier la **vraie** connexion de production sur Render sans divulguer sa valeur.
2. Faire un export chiffré et restreint avec `pg_dump --format=custom --no-owner --no-privileges --file=<chemin_protégé>` depuis un environnement sûr utilisant un compte en lecture seule si possible.
3. Ne jamais joindre ce dump à une issue GitHub ou à un dépôt public. Les utilisateurs et leurs données personnelles sont dans la sauvegarde.
4. Vérifier le dump dans une base isolée, pas la base `production`. Contrôler structure, références, nombre de comptes/treks et cohérence des géométries. Restaurer avec `pg_restore` sur la base isolée.
5. Définir une politique de conservation adaptée aux quotas et à la confidentialité. Le snapshot Neon et l'historique de restauration ne remplacent pas ce dump indépendant.

**Attention à l'API Neon de restauration** : `restore_snapshot` avec `finalize` par défaut peut **permuter les noms de branches et réassigner les computes**, y compris le compute utilisé par Render ! Pour inspecter une copie, utiliser un flux explicitement non finalisé si l'API le permet, vérifier les identifiants d'origine et d'arrivée AVANT l'appel, puis contrôler la branche `production`, la branche par défaut et l'hôte de connexion après. Ne jamais restaurer par défaut sur la production.

Le 13 octobre, une permutation automatique s'est produite pendant une vérification ; l'association initiale du compute, le nom de branche et la branche par défaut ont été rétablis et les comptages revérifiés. Une branche `verification-restauration-20261013` a été conservée temporairement sans endpoint actif.

## Sécurité et contrôle quotidien

- Page `/`, `/health`, `/health/ready`, `/treks`, `/ai/status` ; ne pas prendre un simple HTTP 200 sur `/` pour une confirmation de l'accès base.
- Vérifier qu'une lecture de trek enregistré fonctionne, puis la création/édition via un compte de test, sans modifier les données réelles.
- Surveiller les erreurs API et les limites de fournisseur ORS/Overpass/Photon, et séparer les tests hors ligne des vrais parcours réseau.
- Ne pas enregistrer de mots de passe/DSN dans les logs, artefacts CI ou issues.
- Pour un changement, garder `main` intact tant que les tests de la branche ne sont pas validés ; Render auto-déploie `main` uniquement.

## Risque de facturation

Render et Neon sont sous offres gratuites au moment du constat. Les snapshots, branches supplémentaires, transferts, heures de calcul et API externes peuvent avoir des plafonds : vérifier la consommation avant d'ajouter un cron, un endpoint, une branche longue durée ou une campagne de benchmarks.
