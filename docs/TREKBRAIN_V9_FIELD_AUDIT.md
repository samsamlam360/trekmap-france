# TrekBrain v9 — audit terrain

## Objectif

Cette gate complète les tests spécialisés existants par une batterie transversale
de **40 demandes réalistes**. Elle vérifie la compréhension avant tout appel
réseau afin que les régressions de langage soient détectées vite et de façon
reproductible.

## Défauts trouvés et corrigés

1. Une formulation comme « ce n'est pas une boucle » pouvait être réinterprétée
   en boucle par le parseur historique, après une première interprétation correcte
   par la couche v9.
2. « Départ de X et arrivée à Y » ne forçait pas systématiquement une traversée
   quand le formulaire conservait une ancienne valeur « Boucle ».
3. La formulation naturelle « entre 16 et 20 km par jour » n'était pas comprise
   comme une plage de distance.
4. « Pas de camping, je préfère un refuge » pouvait sélectionner camping à cause
   de la simple présence du mot.
5. Eau, ravitaillement et hébergement exprimés uniquement dans le texte étaient
   moins fiables que les cases du formulaire. Les négations textuelles pouvaient
   également être perdues dans l'audit v9.

## Couverture de la gate terrain

- 10 scénarios de forme d'itinéraire et contradictions ;
- 10 scénarios durée, distance et dénivelé ;
- 15 scénarios difficulté, couchage, transport, eau et ravitaillement ;
- 5 scénarios de réconciliation géographique et formulaire obsolète.

La suite est volontairement sans réseau. Les services externes (ORS, Overpass,
géocodage, recherche) conservent leurs suites de résilience dédiées et le site
déployé est contrôlé séparément par les smoke tests de production.

## Critère de sortie

Une version v9 stable ne doit être déployée que si les 40 scénarios terrain, les
5 golden prompts historiques, les tests géographiques, les tests de résilience,
les tests UI et le préflight Render passent ensemble.
