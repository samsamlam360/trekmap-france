# TrekMap France 5.0 — exploitation

## Vérifications avant mise en ligne

Le build Render applique, dans cet ordre, les couches d’interface puis démarre `backend.app_v5:app`. La route de santé principale est `/health/ready`.

À chaque mise à jour importante, vérifier au minimum :

1. recherche puis ouverture d’un trek ;
2. favoris puis nouvelle recherche ;
3. clic et molette dans la barre des treks ;
4. repli/dépli du panneau de filtres ;
5. import d’un GPX puis édition ;
6. création d’un trek sur la carte ;
7. profil, favoris et préparations ;
8. fiche trek, commentaires, note et téléchargement GPX ;
9. affichage mobile ;
10. `/health`, `/health/ready` et `/treks`.

## Données ajoutées en 5.0

La migration produit ajoute les colonnes `route_type`, `best_season`, `start_name`, `end_name`, `photos` et `points_of_interest` à `treks`, ainsi que la table `trek_ratings`.

Les migrations sont idempotentes et rejouables. Si PostgreSQL est temporairement indisponible au démarrage, elles sont retentées lors du premier appel d’une route 5.0.

## Sauvegardes

La base PostgreSQL reste la source de vérité. Une sauvegarde doit être faite depuis l’hébergeur ou avec `pg_dump` avant une migration manuelle, une suppression massive ou une opération d’administration importante.

Ne jamais stocker un dump de production contenant des comptes utilisateurs dans le dépôt GitHub public.

## Contrôles automatiques

- `TrekMap UI validation` construit toutes les couches, vérifie la syntaxe JavaScript/Python et la présence des routes 5.0.
- `TrekMap nightly health` teste quotidiennement la page publique, `/health`, `/health/ready` et `/treks`.
- `/admin/consistency` permet à un administrateur de vérifier les références orphelines et les treks sans géométrie.

## Retour arrière

En cas de régression d’interface, revenir au dernier commit connu comme stable puis redéployer Render. Les migrations 5.0 n’effacent aucune colonne historique et peuvent rester présentes même si l’interface est temporairement revenue à une version précédente.
