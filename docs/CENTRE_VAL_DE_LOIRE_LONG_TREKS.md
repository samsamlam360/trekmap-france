# Itinérances pédestres Centre-Val de Loire (octobre 2026)

## Nouvelle collecte

**Neuf nouveaux itinéraires pédestres de strictement plus d'un jour** ont été sélectionnés
à partir de relations OpenStreetMap et du service public Waymarked Trails.
Le catalogue vérifié se trouve dans `data/centre_multiday_treks_odbl.json`,
et son périmètre a été validé contre la limite administrative IGN / INSEE
`data/centre_val_de_loire_region.geojson`.

Les neuf traces représentent des **tronçons continus cartographiés** sur le
territoire de Centre-Val de Loire, **pas le parcours national intégral** des GR.
La simplification GPS est contrôlée avec moins de 4 % d'écart de distance,
sans ajout de liaison fictive. Toutes les coordonnées restent dans la région.

| Secteur / source OSM | Distance de la géométrie | Durée indicative |
|---|---:|---:|
| Via Turonensis vers Vendôme | 41,84 km | 3 jours |
| GR 31 Lamotte – La Ferté-Saint-Cyr | 41,61 km | 3 jours |
| Du Cher à la Loire (GR 413) | 54,55 km | 3 jours |
| De Vendôme à la Loire (GR 353) | 59,70 km | 3 jours |
| Tours de Sologne | 81,97 km | 5 jours |
| GR 46 : portion régionale | 84,39 km | 5 jours |
| Chemin de Trèves, Vendôme – Tours | 128,47 km | 7 jours |
| GR 41 : vallée du Cher | 169,72 km | 9 jours |
| GR 31 : traversée de la Sologne | 172,06 km | 9 jours |

Durées estimées, à **20 km/jour**, non publiées comme durées officielles.
Les étapes, nuitées, points d'eau, dénivelé positif et fermetures n'ont pas
été validés : chaque trek l'indique explicitement. Les noms des relations
et le kilométrage sont issus du GPS réellement récupéré.

## Sources et droits

Données ODbL autonomes : © les contributeurs OpenStreetMap,
https://www.openstreetmap.org/copyright ; relations cartographiées via
https://hiking.waymarkedtrails.org/ . Licence Open Database License 1.0.
Chaque trek contient l'URL de sa relation et une clé unique
`Référence : osm-cvl-rel:<id>` ; la publication de ce fichier sous la même licence
et avec attribution conserve la traçabilité et les obligations de partage à l'identique.

Contour de validation : gregoiredavid/france-geojson, dérivé d'IGN Admin Express
et INSEE, Licence Ouverte ; https://github.com/gregoiredavid/france-geojson.

Le protocole de validation ne réutilise pas de photographies ni le fond de carte
de tiers. Le fait qu'une relation existe dans OSM ne prouve pas l'ouverture du
sentier ni l'existence d'un camping ou d'un hébergement.

## Publication

- **Ne pas modifier les treks privés ou existants**. Import additif sur Neon,
  avec vérification des doublons sur `source_key` dans la description.
- Ne jamais importer un itinéraire dont la durée est inférieure ou égale à 1 jour.
- Aucun appel réseau, import ou modification de la base au démarrage de Render.
- Test sur le catalogue : `python scripts/test_centre_multiday_treks.py`.
- Contrôler après publication `GET /treks` et `GET /treks/geojson`,
  sur des objets publics et des traces non vides.
