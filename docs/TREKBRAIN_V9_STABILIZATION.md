# TrekBrain v9 — mode gratuit spécialisé

## État et périmètre

Développement sur `trekbrain-v9-stabilization`. Aucun déploiement ni changement
de la base de production. Les modules v8 et les générateurs UI v8 sont conservés.
Cette version est un assistant déterministe spécialisé avec outils de recherche
et de cartographie, pas un modèle généraliste du niveau de ChatGPT.

## Réalisé

- `TREKBRAIN_VERSION=v8` reste le défaut. Backend et construction UI choisissent
  la même version. La v9 est une activation explicite.
- `TREKBRAIN_FREE_MODE=1` par défaut : pas d'appel Gemini, Google CSE ou Brave,
  même quand des clés existent. Recherche DuckDuckGo best effort. Le routage et
  les données géographiques conservent leurs fournisseurs/configurations.
- Aucun quota d'essais total/journalier ajouté par TrekBrain. Cela ne rend pas
  les services externes ou l'hébergement illimités et ne supprime pas leurs
  restrictions. Les garde-fous de concurrence restent actifs.
- Recherche avec pool partagé de quatre workers, au plus douze travaux en
  attente/exécution, mutualisation des requêtes identiques, cache de 128 entrées.
  Cache positif de dix minutes, réponses vides trente secondes. Le cache est
  limité au processus, non partagé entre plusieurs instances.
- Budget d'attente Web par défaut de huit secondes. Les tâches déjà parties
  finissent avec les timeouts du fournisseur ; aucun nouveau pool par demande.
  Ce budget ne borne PAS toute la génération : le moteur géographique existant
  conserve ses appels réseau et ses retries.
- Pas de téléchargement aveugle des pages trouvées : les extraits et liens sont
  présentés comme pistes, jamais comme confirmation d'ouverture, de disponibilité
  ou de sécurité. Les paramètres d'URL identifiant un événement sont préservés,
  contrairement aux paramètres de suivi.
- Le classement des sources officielles vérifie le domaine, pas une chaîne
  présente dans le chemin de l'URL. Ce classement n'est pas une preuve.
- Audit des jours/distances selon la demande interprétée, tracé absent/dégradé,
  coordonnées invalides, fermeture de boucle à 250 m, maximum quotidien,
  transports incomplets et objectifs importants absents ou au mauvais jour.
  Un défaut bloquant plafonne le score sous 60. Ce score est heuristique.
- Une éventuelle seconde hypothèse privilégie moins de blocages avant le score
  et n'est pas démarrée après le budget de retry (25 s par défaut). Une seconde
  hypothèse déjà lancée n'est pas interrompue par ce budget.
- Une panne de personnalisation ou de stockage des retours ne détruit pas un
  parcours déjà calculé. Authentification et contrôles d'accès restent requis.
- `/ai/ask` authentifié : questions sur eau, nuitées, transports, distances,
  limites et étape numérotée du parcours affiché. Réponse locale sans recherche,
  sans recalcul, sans mémoire de conversation persistante ni invention d'horaires.
  Ce dialogue interprète les données transmises par le client, il ne les certifie
  pas et ne remplace pas la fonction existante de modification du parcours.
- Interface v9 plus lisible, score zéro visible, sortie échappée, délai de
  réponse du dialogue, correction des boucles de rendu du panneau v9 et du
  panneau de recherche hérité (uniquement dans la construction v9).

## Validation locale

```sh
python scripts/test_trekbrain_v8.py
python scripts/test_language_v6.py
python scripts/test_trekbrain_v9.py
python scripts/test_trekbrain_v9_extended.py
node scripts/test_trekbrain_v9_ui.mjs
python -m compileall -q backend scripts
```

Les tests étendus sont hors ligne : erreurs de données, fournisseurs simulés,
cache, deadline, mutualisation, mode sans appels payants, conservation du plan
quand l'apprentissage échoue et dialogue. Le test Node est un test de contrat
DOM, pas un test visuel dans un navigateur réel.

La chaîne de construction frontend a été exécutée dans une copie temporaire ;
les huit scripts inline obtenus ont été vérifiés syntaxiquement. La construction
v9 a aussi été exécutée deux fois pour vérifier son idempotence.
Imports et routes v8/v9 vérifiés dans deux processus distincts avec une URL de
base factice ; aucune connexion à la base de production.

## Avant activation

1. Autoriser puis pousser uniquement la branche dédiée ; ne pas pousser `main`.
2. Exécuter la CI et tester sur une instance séparée, avec `TREKBRAIN_VERSION=v9`
   et `TREKBRAIN_FREE_MODE=1`. Reconstruire l'interface lors du changement de version.
3. Comparer v8/v9 sur les mêmes demandes : boucle, traversée, trajet en train,
   objectif daté, modification d'un plan et fournisseurs indisponibles. Mesurer
   le temps total et les appels réels. Vérifier la carte et l'interface mobile.
4. Ne basculer la production qu'après validation et autorisation. Retour v8 :
   remettre `TREKBRAIN_VERSION=v8` puis reconstruire/redéployer.

## Limites restantes

La recherche gratuite peut échouer ou être limitée. Ni la météo, ni l'état réel
des sentiers, ni les disponibilités des campings, ni les horaires ne sont validés
en direct par le dialogue. Les couches géographiques et linguistiques héritées
ont encore leurs approximations, notamment pour les instructions complexes et
la répartition d'objectifs dans les étapes. Aucune mesure de performance réelle
ou validation terrain n'a été effectuée dans ce lot. Une conversation générale
et flexible nécessiterait un véritable modèle de langage, avec des ressources de
calcul ou un fournisseur : gratuit et illimité ne peut pas être garanti.
