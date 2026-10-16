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
