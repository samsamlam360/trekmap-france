# TrekMap France pour Android : application locale avec outils de randonnée

Ce dossier crée une **vraie application Android installable** avec Capacitor 8, en gardant le site Python/HTML et la base Neon inchangés. Il ne nécessite ni compte Google Play ni ordinateur Android Studio pour produire l'APK, car GitHub Actions le compile.

## Où récupérer l'application ?

Dans GitHub : **Actions > TrekMap Android APK > dernier lancement réussi > Artifacts > trekmap-france-android-debug-…**. Télécharger le ZIP, l'extraire puis installer `app-debug.apk` sur Android. Le téléphone peut demander d'autoriser temporairement l'installation depuis le navigateur ou le gestionnaire de fichiers. Ce build **debug** est pour les tests, pas un APK commercial ni une publication Play Store.

La compilation se lance à chaque PR touchant `mobile/` et après les modifications du dossier sur `main`. Depuis la branche principale, on peut aussi la lancer manuellement via **Run workflow**.

## Fonctionnement technique

- App ID stable : `fr.trekmap.france`. Nom : **TrekMap France**.
- **Nouvelle architecture local-first** : Android ouvre directement l'accueil contenu dans `mobile/www/index.html`, inclus dans l'APK. Il affiche immédiatement les raccourcis carte locale, treks téléchargés, journal GPS et recherche en ligne, même si Render dort. Le bouton « TrekMap en ligne » ouvre ensuite le site HTTPS dans la WebView Capacitor uniquement sur demande.
- La permission GPS est demandée au moment où l'utilisateur démarre l'enregistrement. Le service natif de type localisation reste actif avec notification pendant que l'écran se verrouille. Aucune permission ACCESS_BACKGROUND_LOCATION n'est demandée ; le service doit démarrer depuis l'application visible.
- Le fond de carte MapLibre et ses bibliothèques sont empaquetés localement, avec une activité WebView Android séparée qui bloque toute ressource Internet. **Les tuiles géographiques ne sont disponibles hors ligne qu'après téléchargement par zones**, et les itinéraires doivent être enregistrés depuis le mode randonnée. Sans données enregistrées, le téléphone affiche un écran d'aide, pas une carte de France prétendument téléchargée. Le test sur vrai appareil reste indispensable.
- **Suivi GPS natif expérimental** : depuis « Mode randonnée » l'APK propose « GPS Android · écran verrouillé » et ouvre une interface Android dédiée. L'enregistrement démarre seulement après un clic utilisateur dans cet écran. Pause / reprise / arrêt, distance réelle, écart au tracé, durée et export GPX en local. Le système Android peut malgré tout interrompre le service en cas de restrictions batterie ; validation sur téléphone requise.
- Le `server.url` distant a été retiré. Le shell Capacitor est servi depuis `https://localhost` en HTTPS local. `allowNavigation` est limité à `trekmap-france.onrender.com`. Le plugin Android vérifie l'URL actuelle sur le thread UI : le tableau de bord local ne peut accéder qu'aux fonctions de consultation/navigation native, alors que l'enregistrement des tracés et le suivi GPS par commande JS restent réservés à `/randonnee` sur le site officiel. Le suivi GPS exige toujours un clic distinct.
- Le build GitHub Actions produit un APK signé par la clé **debug temporaire** du runner. Cette clé change : ne pas promettre des mises à jour sans réinstallation. Pour des mises à jour durables, configurer une clé de signature privée persistante dans les Secrets GitHub, jamais dans le dépôt.

## Développement local facultatif

Node.js 22+, Android SDK et JDK 21 :

```bash
cd mobile
npm install
npm run android:add
npm run android:configure
npm run android:sync
npm run android:verify
cd android
./gradlew :app:assembleDebug
```

APK : `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

Si `mobile/android/` existe déjà, sauter `npm run android:add`. Les dossiers `android/` générés et `node_modules/` ne sont pas versionnés : la source de configuration est le dossier `mobile/` et la compilation reproductible GitHub Actions.

## Phase GPS natif (première version expérimentale)

1. Tester ouverture, connexion au compte, fiche trek, carte, import photo et GPS **au premier plan** sur un téléphone Android.
2. Tester le service Android à notification persistante, la pause/reprise après verrouillage, la sauvegarde en stockage privé et l'export GPX, sans serveur de localisation.
3. Relier les positions enregistrées à la page randonnée, en évitant tout pont JS natif accessible à des pages non fiables.
4. Benchmarks batterie, précision, pertes de signal, longues marches et cartographie hors réseau.

**Attention aux mises à jour de l'APK debug :** la clé est régénérée sur chaque runner GitHub et Android peut demander de désinstaller l'ancienne version. Exporte le GPX avant toute désinstallation : les traces du stockage privé seront effacées. Une signature stable devra être créée avec un secret GitHub avant les prochaines versions publiques.

## Mise à jour native sans réinstallation

La partie web de TrekMap France est mise à jour automatiquement via Render : aucun nouvel APK n'est nécessaire. Pour les changements Android, le système inclut désormais une vérification de version GitHub Releases et un installateur natif qui contrôle le SHA-256 avant de proposer l'installation.

**Il manque une étape privée à faire une seule fois** : ajouter la même clé de signature dans les Secrets GitHub. Ne jamais la publier ni l'envoyer dans un chat.

1. Sur un PC, générer et sauvegarder `trekmap-release.jks` avec `keytool -genkeypair -v -keystore trekmap-release.jks -alias trekmap -keyalg RSA -keysize 3072 -validity 10000`. Garder une sauvegarde hors ligne du fichier et des mots de passe.
2. Convertir le fichier .jks en base64 localement (PowerShell : `[Convert]::ToBase64String([IO.File]::ReadAllBytes("trekmap-release.jks"))` ; Linux : `base64 -w0 trekmap-release.jks`).
3. Dépôt GitHub → Settings → Secrets and variables → Actions : ajouter quatre secrets :
   * `TREKMAP_ANDROID_KEYSTORE_BASE64` : chaîne base64 du fichier .jks.
   * `TREKMAP_ANDROID_STORE_PASSWORD` : mot de passe du coffre.
   * `TREKMAP_ANDROID_KEY_ALIAS` : `trekmap`.
   * `TREKMAP_ANDROID_KEY_PASSWORD` : mot de passe de la clé privée.
4. GitHub → Actions → TrekMap Android APK → Run workflow (branche main). Le pipeline publiera une release `android-vNNNN` contenant `trekmap-france.apk`, signée toujours avec la même clé.
5. **Une dernière fois** : sauvegarder les GPX et désinstaller l'ancienne application *debug*, dont la signature ne correspond pas. Installer le premier APK signé. Pour les mises à jour suivantes, ne plus désinstaller : l'application signale la nouvelle version, télécharge son APK vérifié, puis Android demande de confirmer son installation par-dessus.

Les mises à jour système ne peuvent pas être installées silencieusement sans un store ou des droits système spéciaux. L'installation garde les données personnelles de l'application seulement lorsque la signature et l'identifiant de paquet correspondent. Si la clé est perdue, cette continuité de mise à jour est impossible. Tant que les secrets ne sont pas configurés, seule la compilation *debug* est produite et aucune publication signée n'est annoncée.

**Attention** : le code de l'installateur doit être compilé et testé en APK ; la vérification GPS et du téléchargement hors ligne nécessite toujours un essai réel sur le téléphone.

## Android : ouvrir les randonnées enregistrées en mode avion

La WebView distante ne peut pas démarrer si Render est inaccessible. Cette version intègre une **interface Android autonome** qui s'ouvre automatiquement lorsque la connexion réseau n'est pas validée.

Pour préparer : en ligne, ouvre un trek, sélectionne « Mode randonnée » puis « Enregistrer pour Android hors réseau ». Le tracé GPS est enregistré **dans le stockage privé Android**, sans envoyer les coordonnées à Neon. Jusqu'à douze itinéraires peuvent être mémorisés. La réduction à 6 000 points des itinéraires longs peut réduire la précision aux lacets ; c'est un plan de secours, pas un guidage certifié.

En mode avion, rouvre l'application et choisis le trek enregistré : tracé schématique natif, bouton de suivi GPS, calcul des distances, pause et export GPX. La localisation doit rester activée sur le téléphone.

**Limite fondamentale** : ce mode n'inclut **pas encore de fond de carte topographique**, de chemins avoisinants ou de points d'eau. Le téléchargement des tuiles du système web est séparé du stockage natif Android. Prévoir une vraie carte/GPX de secours et ne pas se fier uniquement au tracé simplifié.

## Cartes vectorielles hors réseau sur Android, y compris les grands treks

En Wi-Fi, depuis la fiche trek « Mode randonnée » puis « 🗺️ Télécharger la vraie carte Android ». Enregistre le trek dans le stockage privé, choisis sa section de **25 km**, lance le téléchargement. Recommence pour les sections suivantes. L'application lit les tuiles vectorielles de chemins/forêts/eau depuis des fichiers locaux via AndroidX WebViewAssetLoader, et charge MapLibre GL (JS/CSS) **depuis l'APK**. Le rendu de carte fonctionne en mode avion lorsque les tuiles de la section sont complètes. Les tuiles communes à plusieurs treks sont dédupliquées. Le bouton « Télécharger cette section » reprend les tuiles manquantes après une interruption ou une erreur.

Respect des limites gratuites : maximum **320 tuiles et 24 Mo par action**, séquentiellement (un seul téléchargement en parallèle). Le serveur TrekMap maintient sa limite IP **900 tuiles/heure** : en cas de 429, reprendre plus tard. La protection de stockage local plafonne les fonds téléchargés à **650 Mo** pour éviter de saturer le téléphone. Un trek long peut être téléchargé section par section, sans un plafond global de 480 tuiles ni une durée maximale arbitraire. Le service tiers OpenFreeMap limite lui-même chaque téléchargement à 3 000 tuiles / 50 Mo ; cette application reste en dessous par lot. Voir https://openfreemap.org/quick_start/.

Profil : onglet « Treks téléchargés » (dans l'application Android, compte connecté), qui affiche la liste privée des tracés préparés sur **cet appareil**, indépendamment des données Neon ou de la connexion au compte sur d'autres appareils. La liste hors réseau se retrouve aussi directement au lancement en mode avion. Android affiche une carte **vectorielle interactive** réelle, mais sans libellés de villages ni courbes de niveau, faute de glyphes/relief embarqués. Les zones non préparées restent volontairement vides.

Ne jamais utiliser le fond comme seule preuve de praticabilité d'un chemin. Bien vérifier chaque section, garder un GPX et une autre carte. Les tests CI valident compilation et configuration : il faut encore confirmer sur un vrai appareil la couverture des tuiles et la consommation énergétique.

## Mode randonnée avancé : carte TrekMap locale et plusieurs jours

**Ce qui change :**
- Lorsque le téléphone n'a pas Internet, TrekMap ouvre par défaut **la carte locale** (si au moins un trek a été préparé). Elle affiche **tous les itinéraires Android sauvegardés** sur le même fond vectoriel. La barre de sélection, les cartes détaillées, le style vert TrekMap et les statistiques sont inclus **dans l'APK**, sans script réseau.
- Boutons : choisir un trek, voir tout le parcours, suivre le GPS au centre, orientation dans le sens de la marche lorsque le GPS fournit un cap valide, réduire le panneau d'informations, ouvrir le suivi GPS et télécharger les cartes manquantes.
- La carte affiche le nombre de km restants et parcourus, la section en cours (sections de 25 km), le statut GPS et les repères personnels. Elle ne montre pas encore les noms des villes ou les courbes de niveau car les glyphes et modèles de relief ne sont pas embarqués.
- Le GPS natif conserve le cumul des kilomètres, le temps de marche, une vitesse moyenne, l'ascension estimée **sous réserve de précision verticale**, le jour courant et les précédents. « Nouvelle journée » conserve la trace complète.
- À la fin, les GPX sont sauvegardés localement (24 sorties récentes maximum). Dans le carnet GPS Android, on peut exporter un GPX et ajouter une image JPG/PNG/WebP de moins de 5 Mo à une sortie. Les photos et les traces ne sont pas transférées sur Render/Neon.
- La notification du service Android permet de mettre en pause, puis de reprendre. En cas d'interruption du processus, on peut relancer manuellement le suivi ; **Android ne garantit pas un suivi continu si les restrictions batterie tuent le service**.
- Un écart à l'itinéraire doit être confirmé par **3 positions fiables** ; vibration optionnelle (permission Android) avec une fréquence plafonnée. Les repères eau/refuge/ravitaillement sont créés **manuellement** depuis une position GPS, pas des confirmations d'ouverture, de potabilité ou d'accessibilité.

**Limites non résolues** : uniquement une carte vectorielle locale avec ses tuiles effectivement téléchargées ; certaines zones restent vides si la préparation est incomplète. Le tracé réduit à 6 000 points peut perdre des détails. Les photos du carnet natif ne sont pas synchronisées avec le compte web. La détection du retour au tracé reste une estimation GPS, non un conseil de sécurité. Vérifier la carte/GPX de secours avant toute randonnée et tester en conditions réelles avant usage.

## Vers Google Play (AAB)

Sur la branche `main`, quand les quatre secrets de signature privée `TREKMAP_ANDROID_KEYSTORE_BASE64`, `TREKMAP_ANDROID_STORE_PASSWORD`, `TREKMAP_ANDROID_KEY_PASSWORD` et `TREKMAP_ANDROID_KEY_ALIAS` ont été configurés, le workflow GitHub Actions construit **en plus de l'APK de test** un Android App Bundle signé `app-release.aab` : `Actions > TrekMap Android APK > Artifacts > trekmap-france-play-aab-…`.

Le bundle Google Play exclut la permission sensible `REQUEST_INSTALL_PACKAGES`, propre au système historique de mises à jour APK. Une installation distribuée par Google Play n'affiche pas le mécanisme de mise à jour latérale GitHub : les mises à jour passent par Google Play.

**Pas encore prêt à publier sans validation complémentaire** : tester la nouvelle interface locale et toutes les commandes natives sur un vrai téléphone, vérifier les règles de confidentialité et les déclarations Play, préparer la fiche Play Store, et contrôler la signature et le SDK cible au moment de la publication. L'APK debug généré en PR n'est pas destiné à Google Play. Ne jamais exposer les clés de signature dans le dépôt.

## Utilisation hors réseau

1. Ouvrir l'application : l'accueil local est disponible sans attendre Render.
2. Appuyer sur « Ouvrir ma carte » : l'activité Android hors ligne affiche les tracés sauvegardés.
3. Pour préparer une randonnée, se connecter au site via « TrekMap en ligne », ouvrir le trek, puis « Mode randonnée » et enregistrer le tracé sur le téléphone.
4. Télécharger **toutes les sections et tuiles** du trek pendant une connexion Wi-Fi ; vérifier que chaque section est complète.
5. Activer le mode avion et tester carte, trajets, suivi GPS et retour vers l'accueil local **avant** toute randonnée réelle. Les nouveaux treks, comptes et TrekBrain ne sont pas fonctionnels hors réseau.
6. Un appui sur « Retour » de la carte Android revient désormais à l'accueil local. Le passage en ligne est volontaire et exige une connexion validée.

Ce mode ne prétend pas charger tous les treks de France ni toutes les cartes hors réseau. Les données enregistrées peuvent être perdues si l'application est désinstallée : exporter les GPX importants avant de désinstaller.
