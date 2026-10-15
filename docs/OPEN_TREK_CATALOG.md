# Itinéraires publics sous licence ouverte

Le jeu source `data/catalogue_open_treks.json` conserve **140 tracés historiques** publiés par quatre organismes publics à des fins de provenance et de contrôle. Il ne reflète **pas** automatiquement les itinéraires actuellement affichés dans TrekMap : après la suppression demandée des 123 sorties de moins d’un jour, **17 parcours de cette première collecte restent publiés**. Les **35 longs treks** ajoutés ensuite restent disponibles et les deux petits treks personnels ont été préservés. La table `treks` de Neon est la référence du catalogue public.

## Sources et droits

- Métropole de Lyon : [boucles communales](https://www.data.gouv.fr/datasets/boucles-communales-de-randonnee-de-la-metropole-de-lyon-1) (Licence Ouverte 2.0).
- Parc national des Écrins : [randonnées estivales](https://www.data.gouv.fr/datasets/randonnees-du-parc-national-des-ecrins) (Licence Ouverte 2.0).
- Lannion-Trégor : [randonnées pédestres](https://www.data.gouv.fr/datasets/itineraires-de-randonnee-pedestre-de-lannion-tregor-communaute) (Licence Ouverte 2.0, 35 parcours validés par raccordement d'extrémités jointives).
- Parc national des Cévennes : [itinéraires de randonnée](https://www.data.gouv.fr/datasets/itineraires-de-randonnee-du-parc-national-des-cevennes) (Licence Ouverte, 35 parcours validés).
- Département du Calvados : [circuits qualité](https://www.data.gouv.fr/datasets/itineraires-de-randonnee-circuits-qualite-departement-du-calvados) (Licence Ouverte 2.0, source momentanément inaccessible).

Attribution obligatoire : **© les producteurs cités ci-dessus, Licence Ouverte 2.0**. Une mention propre à chaque trek figure dans sa description avec le lien du jeu et son identifiant d'import.

Ce jeu est séparé des treks personnels des utilisateurs. Aucun itinéraire n'est créé par une IA.

## Vérifications

- Un trajet doit être une ligne continue en latitude/longitude en France, comporter au moins trois positions et mesurer entre 2 et 90 km.
- Les MultiLineString sont raccordés uniquement si les extrémités réelles sont jointives à 25 mètres près ; les composants discontinus ou en branche ne sont pas raccordés artificiellement et sont rejetés.
- La géométrie est simplifiée sans points inventés ; une variation de plus de 5 % de longueur est rejetée.
- La distance est calculée sur les coordonnées **avant** simplification. La difficulté n'est que celle du fournisseur si elle est présente ; sinon une valeur conventionnelle est utilisée et la fiche avertit que la difficulté n'est pas vérifiée.
- Si le fournisseur ne communique pas le dénivelé, la valeur technique 0 doit être lue **« non renseigné »**, et surtout pas « terrain plat ».
- L'identifiant de provenance et le texte d'attribution évitent d'importer deux fois la même trace. Les utilisateurs existants et leurs treks privés ne sont jamais modifiés.

## Exploitation

`python scripts/prepare_open_treks.py` télécharge cinq fichiers de données ouvertes, produit localement un catalogue JSON contrôlé et **n'écrit jamais dans Neon**. Le workflow GitHub n'exécute cet import que sur une branche de revue. Les fichiers générés sont inclus dans GitHub avant diffusion ; aucun téléchargement supplémentaire n'est lancé au démarrage de Render.

Pour publier dans la table `treks` de Neon : enregistrer uniquement les itinéraires validés, avec `owner_id` rattaché au compte administrateur, `is_public=true` **et `duration_days >= 1`**. Les anciens itinéraires publics de moins d'un jour ne doivent **pas être réimportés** depuis le jeu historique. Les écrits sont additifs, idempotents et soumis aux contrôles de santé habituels. Chaque étape vérifie le nombre de lignes publiées et l'intégrité des géométries. Le processus ne modifie ni les comptes ni les parcours existants.

Les voies et espaces naturels évoluent. La présence dans TrekMap n'est **pas une garantie de praticabilité**. Consultez les autorités locales, restrictions saisonnières et conditions météo avant de partir.
