# TrekBrain v9 : refonte ergonomique fondée sur des recherches

**Contexte** : assistant de randonnée sur TrekMap France. L'interface doit aider à
écrire une demande, choisir les contraintes, comprendre les itinéraires et
repérer ce qui reste à vérifier sur le terrain, sans masquer les avertissements.

## Travaux scientifiques et recommandations ergonomiques

1. **Divulgation progressive (Jakob Nielsen, Nielsen Norman Group, 2006)** :
   montrer d'abord les options nécessaires, puis laisser l'utilisateur accéder
   à des fonctions plus rares. Source :
   https://www.nngroup.com/articles/progressive-disclosure/
   - Application : la demande, la région, la durée et les km/j restent visibles.
     Difficulté, type de parcours et critères logistiques sont dans
     « Personnaliser mon trek ». Leurs valeurs restent préservées dans le DOM.
2. **Usabilité des formulaires mobiles (Baymard Institute)** : des labels
   explicites près des champs et un nombre limité de champs à gérer réduisent
   les erreurs dans la saisie. Les observations concernent avant tout le
   commerce ; leur transfert au contexte randonnée est une *hypothèse UX*,
   non une amélioration mesurée ici.
   - https://baymard.com/research-articles/mobile-ecommerce-checkout-forms
   - https://baymard.com/research-articles/checkout-flow-average-form-fields
   - Application : indications courtes, exemples de prompts modifiables,
     espaces entre les champs, pas de remplacement des champs libres.
3. **WCAG 2.2 critère 2.5.8 (W3C/WAI)** : cible d'au moins 24 px en largeur
   et hauteur ou espacement suffisant. Source :
   https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum
   - Application : objectif conservateur de 44–54 px pour les principales
     commandes du dialogue, focus clavier visible, contraste renforcé.
     Cette règle CSS ne constitue pas à elle seule un audit WCAG complet.
4. **Préférences de réduction des animations** : compatibilité
   « prefers-reduced-motion » (respect des paramètres d'accessibilité).
   - https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions

## Choix d'interface

- Palette vert forêt et fond minéral clair, sans importer de police ni de
  bibliothèque payante.
- Deux panneaux lisibles sur ordinateur ; un panneau à la fois sur mobile.
- Bouton principal plus accessible au pouce, exemples modifiables sans lancer
  automatiquement un itinéraire, réglages avancés accessibles au clavier.
- Étapes affichées par cartes avec distances, hébergements et eau non potable
  visuellement distincts ; les avertissements restent visibles.
- Pas de modification des contrats réseau, itinéraires, algorithmes, Neon ou
  coûts Render.

## Validation objective prévue

- **Technique** : génération HTML complète, syntaxe JS, contrôle des identifiants
  de champs, maintien du panneau carte, tests existants, préflight Python.
- **Accessibilité** : audit axe/WCAG, test clavier complet, zoom 200 %,
  lecteur d'écran et largeur 320 px avant de prétendre à une conformité.
- **Utilisateurs** : au moins 5 participants débutants et expérimentés,
  tâches « préparer une boucle », « préciser l'eau », « modifier l'étape 2 »,
  « voir la carte », « comprendre une nuitée avec transfert ».
  Mesurer taux de réussite, erreurs, durée par tâche et satisfaction
  (SUS si le panel est suffisant), avant/après avec ordre contrebalancé.

**Aucune amélioration de conversion ou de satisfaction n'est présumée sans test.**
