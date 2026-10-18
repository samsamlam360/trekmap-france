/**
 * TrekMap France - relais Gmail pour les e-mails de récupération.
 *
 * Déploiement :
 * 1. Créer un projet sur https://script.google.com/
 * 2. Coller ce fichier dans Code.gs.
 * 3. Paramètres du projet > Propriétés du script :
 *    TREKMAP_RELAY_TOKEN = un secret long et aléatoire (au moins 32 caractères).
 * 4. Déployer > Nouveau déploiement > Application Web.
 *    Exécuter en tant que : Moi.
 *    Qui a accès : Tout le monde.
 * 5. Copier l'URL de l'application Web dans GMAIL_RELAY_URL sur Render.
 *    Mettre le même secret dans GMAIL_RELAY_TOKEN sur Render.
 *
 * L'URL est publique, mais les requêtes ne sont acceptées qu'avec le secret.
 * Ne jamais enregistrer le secret dans le code source ou les journaux.
 */
function doPost(e) {
  try {
    const props = PropertiesService.getScriptProperties();
    const expected = props.getProperty('TREKMAP_RELAY_TOKEN') || '';
    if (expected.length < 32) {
      return json_({ ok: false, error: 'relay_not_configured' });
    }

    const payload = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (!payload.token || !constantTimeEqual_(String(payload.token), expected)) {
      return json_({ ok: false, error: 'unauthorized' });
    }

    const to = String(payload.to || '').trim();
    const subject = String(payload.subject || '').trim();
    const body = String(payload.body || '');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to) ||
        subject !== 'Réinitialiser ton mot de passe TrekMap' ||
        body.length < 20 || body.length > 12000) {
      return json_({ ok: false, error: 'invalid_payload' });
    }

    GmailApp.sendEmail(to, subject, body, { name: 'TrekMap France' });
    return json_({ ok: true });
  } catch (err) {
    // Ne pas retourner de données personnelles ni de secret dans la réponse.
    return json_({ ok: false, error: 'send_failed' });
  }
}

function json_(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function constantTimeEqual_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
