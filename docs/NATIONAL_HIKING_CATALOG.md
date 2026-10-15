# Couverture nationale des treks pédestres

## État cible de la collecte du 15 octobre 2026

Après import et vérification de la carte, TrekMap France propose des randonnées de **1 jour minimum dans les 13 régions métropolitaines**. Cette nouvelle étape privilégie les régions qui avaient peu ou pas d'itinéraires. Les 60 treks publics existants doivent rester préservés et 20 nouveaux parcours sont attendus.

- **12 itinéraires des producteurs publics**, présents dans `data/national_curated_long_treks.json` : 8 en Auvergne-Rhône-Alpes, 2 en Pays de la Loire, 1 en Centre-Val de Loire et 1 en Nouvelle-Aquitaine. Sources individuelles et Licence Ouverte 2.0 figurent dans chaque fiche.
- **8 parcours fondés sur des relations OpenStreetMap** : 1 en Bretagne, 1 en Bourgogne-Franche-Comté, 1 dans le Grand Est, 1 dans les Hauts-de-France, 1 en Île-de-France et 3 en Corse. Leurs détails et leurs tronçons géographiques sont contenus séparément dans `data/osm_regional_treks_odbl.json`.

## Licence et attribution

La collection gouvernementale suit la **Licence Ouverte 2.0** avec attribution nominative du producteur et de son jeu sur data.gouv.fr.

La collection OpenStreetMap forme un **sous-ensemble autonome sous Open Data Commons Open Database License (ODbL) 1.0**. **© les contributeurs OpenStreetMap**, https://www.openstreetmap.org/copyright. Tracés publiés à partir de relations ouvertes, consultables sur https://hiking.waymarkedtrails.org/. Le fichier `data/osm_regional_treks_odbl.json` reste publiquement récupérable dans le dépôt GitHub et doit être redistribué avec cette même attribution et les obligations de partage à l'identique. Il ne transforme pas les autres données indépendantes en données ODbL.

Les traces sont des **données de cartographie**, pas des itinéraires homologués par l'office du tourisme, ni des garanties de praticabilité. Les tronçons dont les relations contiennent des variantes ou des branches sont marqués « tronçon continu ». Le calcul de distance et de durée correspond au segment effectivement affiché. Les données de plusieurs jours ne comprennent **pas** de nuits, de points d'eau, de bivouac ou d'étapes inventés.

## Sécurité des imports

1. **Ne jamais republier** les 123 petites randonnées administratives retirées à la demande du propriétaire : seules les données avec `duration_days >= 1` peuvent enrichir le catalogue.
2. Ne pas modifier les parcours personnels, les listes d'aventures, favoris ou collections ; ne jamais supprimer des données à l'aide de ce pipeline.
3. Rejeter un parcours si le GPS est absent, fragmenté sans composante continue suffisante, hors France, incohérent, ou si la licence n'est pas identifiable.
4. Éviter les doublons sur `Référence : <source_key>` et sur le couple `(name,region)`.
5. Effectuer les importations **hors build Render**, de façon additivement idempotente, sur le Neon existant. Pas de services payants.
6. Le test de production `.github/workflows/production-smoke.yml` vérifie, après chaque déploiement, la présence des 13 régions et des 20 nouveaux itinéraires dans les réponses `/treks` et `/treks/geojson`, tout en préservant TrekBrain.

## Couverture et limites

« Couvert » signifie ici qu'au moins un itinéraire public d'une journée ou plus est réellement présent dans chaque région, **pas** que le nombre de randonnées est déjà équitable entre toutes les régions. Certaines régions n'auront encore qu'un ou deux treks. Un futur enrichissement devra augmenter la densité avec des sources ouvertes locales et améliorer les dénivelés ainsi que les informations d'étapes.
