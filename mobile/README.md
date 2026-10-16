# TrekMap France pour Android (premier APK de test)

Ce dossier crée une **vraie application Android installable** avec Capacitor 8, en gardant le site Python/HTML et la base Neon inchangés. Il ne nécessite ni compte Google Play ni ordinateur Android Studio pour produire l'APK, car GitHub Actions le compile.

## Où récupérer l'application ?

Dans GitHub : **Actions > TrekMap Android APK > dernier lancement réussi > Artifacts > trekmap-france-android-debug-…**. Télécharger le ZIP, l'extraire puis installer `app-debug.apk` sur Android. Le téléphone peut demander d'autoriser temporairement l'installation depuis le navigateur ou le gestionnaire de fichiers. Ce build **debug** est pour les tests, pas un APK commercial ni une publication Play Store.

La compilation se lance à chaque PR touchant `mobile/` et après les modifications du dossier sur `main`. Depuis la branche principale, on peut aussi la lancer manuellement via **Run workflow**.

## Fonctionnement technique

- App ID stable : `fr.trekmap.france`. Nom : **TrekMap France**.
- L'application Android charge exclusivement `https://trekmap-france.onrender.com` dans une WebView native. Ainsi comptes, données, TrekBrain et interface restent sur le site existant et continuent d'évoluer sans deux copies divergentes.
- Seuls **Internet** et la localisation **au premier plan** sont déclarés. Le code Android demande à l'utilisateur la permission GPS au moment nécessaire. Aucun accès GPS permanent n'est ajouté.
- Le fond de carte hors ligne actuel de TrekMap reste une fonctionnalité **web** : son fonctionnement dans la WebView Android et la reprise hors connexion doivent encore être testés en conditions réelles. Le chargement initial du site nécessite le réseau et le démarrage hors réseau n'est **pas garanti** pour cet APK initial.
- **Le suivi GPS en arrière-plan / écran verrouillé n'existe pas encore**. La prochaine phase devra ajouter un service Android natif au premier plan, avec notification visible et contrôles démarrer/pause/arrêter. Ne pas prétendre qu'une WebView réalise ce suivi seule.
- Le `server.url` de Capacitor est habituellement destiné au développement : **ce choix provisoire conserve un seul site fonctionnel et le backend déjà déployé**, sans exposer pour l'instant de plugin natif sensible au contenu distant. Avant une publication officielle, remplacer cette architecture par des ressources locales + API compatible, ou un conteneur navigateur sans pont natif accessible au contenu distant, et prévoir des vérifications de sécurité.
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

## Étape suivante : GPS natif

1. Tester ouverture, connexion au compte, fiche trek, carte, import photo et GPS **au premier plan** sur un téléphone Android.
2. Mettre en place le suivi GPS natif au premier plan avec notification Android, reprise après verrouillage, sauvegarde locale chiffrée ou privée, sans serveur de localisation.
3. Relier les positions enregistrées à la page randonnée, en évitant tout pont JS natif accessible à des pages non fiables.
4. Benchmarks batterie, précision, pertes de signal, longues marches et cartographie hors réseau.
