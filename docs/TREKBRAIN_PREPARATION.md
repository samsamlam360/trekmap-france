# Préparation des treks : critères et contrôles v9

Un tracé pédestre valide peut conserver des besoins non résolus. Le champ public `trip_readiness`, ajouté après les couches de sécurité, de ressources et d'interprétation de la demande, distingue :

- `ready` — besoins confirmés dans les références disponibles ;
- `incomplete` — tracé conservé, avec jours/besoins manquants et actions de modification ;
- `refused` — tracé ou contrainte explicite non validés.

Ce verdict ne garantit pas les ouvertures, réservations, horaires ni l'état actuel de l'eau. Il ne modifie pas la géométrie ni les kilomètres calculés. Le score heuristique reste séparé.

## Preuves utilisées

- Eau : identité OSM, coordonnées et journée réelles, proximité du tracé et statut `potable_referenced`. Les tags négatifs ou l'accès interdit priment ; la potabilité inconnue reste visible mais ne confirme pas une journée.
- Ravitaillement : commerce alimentaire OSM identifié et proche de la journée.
- Nuitées : source et position, affectation à la vraie fin d'étape, aller et retour pédestres validés. Un transfert reste incomplet tant qu'il n'est pas confirmé. Une référence d'hébergement n'est pas une réservation.
- Distances : kilomètres réels, y compris les accès à pied lorsqu'ils sont présents. Les limites réellement déclarées ne sont pas remplacées par les bornes calculées. Un objectif approximatif trop dépassé entraîne une préparation incomplète et des propositions de nouvelle demande.
- Objectifs obligatoires : un objectif encore non satisfait reste visible, même avec un score élevé.
- Géographie : les qualifiants écrits, notamment les départements, restent présents. `request_resolution.geocoding` conserve les fournisseurs, points sélectionnés et raisons de rejet dans un contexte isolé par requête.

La validation quotidienne lit `map_resources.evidence_points`, pas uniquement les 48 icônes affichées. Une panne de fournisseur reste distincte d'une recherche ayant répondu sans référence.

## Budgets et données

La recherche de variantes de distance ajoute au plus deux appels bornés. La logistique des nuitées valide au plus une Matrix et deux Directions directes, dans le budget restant, sans relances cachées ni worker abandonné. Les connecteurs restent séparés du parcours principal.

Aucune nouvelle base, migration ou clé payante n'est créée. Les tests utilisent une base fictive et des fournisseurs simulés. Aucun gros benchmark réseau n'est lancé pendant un build Render ou sur chaque push.

## Benchmarks

Les rapports distinguent `structure_ok`, `preparation_ok` et `ok`. Les suites continuent après un cas refusé ou incomplet et conservent les rapports avant de rendre le verdict global.

Le workflow manuel `trekbrain-cold-benchmark.yml` nécessite un secret GitHub existant nommé `ORS_API_KEY`. Il ne copie pas la clé Render et n'en crée pas. Sans ce secret, il produit un rapport `configuration_error` avant tout appel fournisseur.

Le test à froid utilise quatre processus frais, une base isolée, le cache OSM applicatif désactivé, des cas de 90 secondes maximum et une campagne de 400 secondes maximum. Les caches propres aux fournisseurs externes restent hors de son contrôle.

## Vérification locale

Les nouvelles régressions couvrent les besoins par journée, les faux positifs de preuve, les nuitées après une lacune, les vrais points de fin d'étape, les limites minimum/maximum, les homonymes, l'isolation de la trace, le nombre réel d'appels ORS et les actions de l'interface.

Les registres CI et préflight incluent ces contrôles hors réseau. Les tests de l'interface exécutent les fonctions JavaScript des générateurs réels ; le build du frontend vérifie également la syntaxe des scripts générés.
