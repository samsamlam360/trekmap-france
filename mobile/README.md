# TrekMap France pour Android (premier APK de test)

Ce dossier crée une **vraie application Android installable** avec Capacitor 8, en gardant le site Python/HTML et la base Neon inchangés. Il ne nécessite ni compte Google Play ni ordinateur Android Studio pour produire l'APK, car GitHub Actions le compile.

## Où récupérer l'application ?

Dans GitHub : **Actions > TrekMap Android APK > dernier lancement réussi > Artifacts > trekmap-france-android-debug-…**. Télécharger le ZIP, l'extraire puis installer `app-debug.apk` sur Android. Le téléphone peut demander d'autoriser temporairement l'installation depuis le navigateur ou le gestionnaire de fichiers. Ce build **debug** est pour les tests, pas un APK commercial ni une publication Play Store.

La compilation se lance à chaque PR touchant `mobile/` et après les modifications du dossier sur `main`. Depuis la branche principale, on peut aussi la lancer manuellement via **Run workflow**.

## Fonctionnement technique

- App ID stable : `fr.trekmap.france`. Nom : **TrekMap France**.
- L'application Android charge exclusivement `https://trekmap-france.onrender.com` dans une WebView native. Ainsi comptes, données, TrekBrain et interface restent sur le site existant et continuent d'évoluer sans deux copies divergentes.
- La permission GPS est demandée au moment où l'utilisateur démarre l'enregistrement. Le service natif de type localisation reste actif avec notification pendant que l'écran se verrouille. Aucune permission ACCESS_BACKGROUND_LOCATION n'est demandée ; le service doit démarrer depuis l'application visible.
- Le fond de carte hors ligne actuel de TrekMap reste une fonctionnalité **web** : son fonctionnement dans la WebView Android et la reprise hors connexion doivent encore être testés en conditions réelles. Le chargement initial du site nécessite le réseau et le démarrage hors réseau n'est **pas garanti** pour cet APK initial.
- **Suivi GPS natif expérimental** : depuis « Mode randonnée » l'APK propose « GPS Android · écran verrouillé » et ouvre une interface Android dédiée. L'enregistrement démarre seulement après un clic utilisateur dans cet écran. Pause / reprise / arrêt, distance réelle, écart au tracé, durée et export GPX en local. Le système Android peut malgré tout interrompre le service en cas de restrictions batterie ; validation sur téléphone requise.
- Le `server.url` de Capacitor est habituellement destiné au développement. Pour l'APK de test, le seul plugin natif accepte une requête d'ouverture **uniquement** depuis `https://trekmap-france.onrender.com/randonnee`; il ne démarre pas le GPS, ne renvoie jamais de coordonnées et nécessite un clic d'enregistrement natif distinct. Pour une publication officielle, servir les ressources locales et auditer le pont WebView.
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
