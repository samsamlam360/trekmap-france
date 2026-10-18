# Relais Gmail pour TrekMap France

Ce relais permet au backend hébergé sur Render d'envoyer les liens de récupération via l'API HTTPS d'une application Google Apps Script. Il évite les ports SMTP sortants bloqués sur les services Render gratuits.

## Installation

1. Créer une boîte Gmail dédiée à TrekMap France.
2. Ouvrir https://script.google.com/ et créer un projet Apps Script.
3. Copier le contenu de `Code.gs` dans l'éditeur.
4. Dans **Paramètres du projet > Propriétés du script**, ajouter :
   - Nom : `TREKMAP_RELAY_TOKEN`
   - Valeur : un secret aléatoire long (au moins 32 caractères). Générer une valeur distincte, ne pas la publier ni la mettre dans GitHub.
5. Cliquer **Déployer > Nouveau déploiement > Application Web** :
   - Exécuter en tant que : **Moi**
   - Qui a accès : **Tout le monde**
6. Autoriser les permissions Gmail demandées par Google et copier l'URL de l'application Web.
7. Après fusion de la PR, dans les variables d'environnement du service Render, définir :
   - `GMAIL_RELAY_URL` : URL de l'application Web Apps Script
   - `GMAIL_RELAY_TOKEN` : la même valeur secrète que dans les propriétés du script

Ne pas ajouter de guillemets autour des valeurs. Ne jamais communiquer le secret dans le chat ni le committer dans GitHub.

## Vérification

- L'endpoint `/auth/password/status` doit retourner `email_reset_available: true` après redémarrage avec les variables configurées.
- Demander une réinitialisation pour un compte de test et vérifier la boîte de réception et les courriers indésirables.
- Ne considérer la fonction prête qu'après réception effective et test du lien à usage unique.

## Limites

Les quotas d'envoi Gmail/Apps Script s'appliquent. Cette solution convient au lancement et à un faible volume ; si TrekMap prend de l'ampleur, utiliser un fournisseur transactionnel avec un domaine authentifié.
