"""Finaliser accueil/TrekBrain et proposer la récupération du compte.

Couche UI additive : aucun raccourci GPS ni action de TrekBrain remplacés.
Le serveur fournit les seuls jetons de récupération, par email.
"""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
path=root/'frontend'/'index.html'
html=path.read_text(encoding='utf-8')
html=re.sub(r'\s*<!-- TM_FINISH_RECOVERY_START -->.*?<!-- TM_FINISH_RECOVERY_END -->\s*','\n',html,flags=re.S)
for marker in ['TM_DETAIL_PROFILE_POLISH_START','TREKMAP_FOUR_SPACES_START','TREKMAP_PROFILE_V2_START']:
    if marker not in html:raise SystemExit('UI finish prerequisite missing: '+marker)
block=r'''<!-- TM_FINISH_RECOVERY_START -->
<style id="tm-finish-recovery-css">
/* Accueil : moins de cadres concurrents et une hiérarchie visuelle régulière. */
.tm-home{color:#173a2b}
.tm-home :is(button,a,input,select):focus-visible{outline:3px solid #f1c151!important;outline-offset:3px}
.tm-home :is(.tm-home-card,.tm-home-feature,.tm-home-quick-item){
 border-radius:16px;transition:transform .16s ease,box-shadow .16s ease}
.tm-home :is(.tm-home-card,.tm-home-feature,.tm-home-quick-item):hover{transform:translateY(-2px)}
.tm-home h1{letter-spacing:-.03em;line-height:1.1}
.tm-home h2{letter-spacing:-.02em}
.tm-home .tm-home-search input{font-size:16px;min-height:48px}
/* TrekBrain: texte et cartes lisibles de la même manière que les fiches de trek. */
#tm-ai-overlay :is(input,select,textarea,button){font-family:inherit}
#tm-ai-overlay :is(input,select,textarea){border-radius:11px;min-height:44px}
#tm-ai-overlay :is(button,input,select,textarea):focus-visible,
#tm-brain-route-panel :is(button,input,select,textarea):focus-visible{
 outline:3px solid #f0bb4b!important;outline-offset:2px}
#tm-ai-overlay h2,#tm-brain-route-panel h2{letter-spacing:-.025em}
#tm-brain-route-panel :is(.tm-brain-card,.tm-brain-day-card,.tm-brain-stage){
 border-radius:15px}
/* Bouton mot de passe oublié dans la modale de connexion. */
#tm-forgot-link{appearance:none;cursor:pointer;border:0;background:transparent;
 color:#116441;text-decoration:underline;text-underline-offset:3px;min-height:44px;
 padding:9px 2px;text-align:left;font-size:13px;font-weight:770}
#tm-forgot-link:focus-visible{outline:3px solid #f0bb4b;outline-offset:3px}
#tm-recovery-modal{display:grid;gap:12px}
#tm-recovery-modal p{margin:0;font-size:13px;line-height:1.55;color:#466a53}
#tm-recovery-modal label{display:grid;gap:7px;color:#164b31;font-weight:790;font-size:13px}
#tm-recovery-modal input{width:100%;min-height:48px;border:1px solid #bfd6c7;
 border-radius:10px;background:#fff;color:#173b2a;font:inherit;font-size:16px;padding:11px}
#tm-recovery-modal button{min-height:45px;border:1px solid #bed8c8;border-radius:11px;
 background:#f1f8f3;color:#135b3b;font-weight:790;cursor:pointer;padding:9px 13px}
#tm-recovery-modal button.primary{background:#147c53;color:#fff;border-color:#147c53}
#tm-recovery-modal button[disabled]{opacity:.55;cursor:default}
#tm-recovery-modal .tm-recovery-actions{display:flex;flex-wrap:wrap;gap:8px}
#tm-recovery-modal [role="status"]{min-height:23px;font-size:13px;font-weight:650;
 color:#255e3e;overflow-wrap:anywhere}
#tm-recovery-modal [role="status"].error{color:#9f3e2e}
#tm-profile-v2 .tm-library-categories{position:relative}
@media(max-width:780px){
 .tm-home :is(.tm-home-card,.tm-home-feature,.tm-home-quick-item):hover{transform:none}
 #tm-recovery-modal .tm-recovery-actions button{flex:1 1 130px}
}
@media(prefers-reduced-motion:reduce){
 .tm-home :is(.tm-home-card,.tm-home-feature,.tm-home-quick-item){transition:none!important}
}
</style>
<script id="tm-finish-recovery-js">
(function(){
 'use strict';
 if(window.TrekMapRecoveryUI)return;
 var $=function(id){return document.getElementById(id)};
 var modal=$('modal');
 if(!modal)return;
 function openTemplate(title,body){
  if(typeof openModal!=='function')return false;
  openModal('<div class="modal-head"><h2>'+title+'</h2><button type="button" class="close" id="modal-close" aria-label="Fermer">✕</button></div>'+
   '<div id="tm-recovery-modal">'+body+'</div>');
  $('modal-close').onclick=closeModal;
  return true;
 }
 function status(message,error){
  var box=$('tm-recovery-status');if(!box)return;
  box.textContent=message||'';box.classList.toggle('error',!!error);
 }
 function addButton(id,label,parent){
  var button=document.createElement('button');button.type='button';button.id=id;
  button.textContent=label;parent.appendChild(button);return button;
 }
 async function post(path,payload,button){
  button.disabled=true;
  try{
   var response=await fetch('/auth/password/'+path,{method:'POST',credentials:'same-origin',
    headers:(typeof headers==='function'?headers({'Content-Type':'application/json'},'POST'):{'Content-Type':'application/json'}),body:JSON.stringify(payload),cache:'no-store'});
   var data=await response.json().catch(function(){return {}});
   if(!response.ok)throw Error(data.detail||'Service momentanément indisponible.');
   return data;
  }finally{button.disabled=false}
 }
 function openForgot(){
  if(!openTemplate('Mot de passe oublié',
   '<p>Renseigne l’adresse e-mail de ton compte pour recevoir un lien à usage unique.</p>'+
   '<label>E-mail du compte<input id="tm-forgot-email" type="email" autocomplete="email" required maxlength="255" placeholder="adresse@exemple.fr"></label>'+
   '<div role="status" aria-live="polite" id="tm-recovery-status"></div>'+
   '<div class="tm-recovery-actions"><button type="button" id="tm-recovery-back">Retour à la connexion</button>'+
   '<button type="button" class="primary" id="tm-recovery-send">Envoyer le lien</button></div>'))return;
  $('tm-recovery-back').onclick=function(){authModal('login')};
  var submit=$('tm-recovery-send');
  submit.onclick=async function(){
   var email=$('tm-forgot-email');
   if(!email.reportValidity())return;
   status('Envoi de la demande…',false);
   try{
    var data=await post('forgot',{email:email.value.trim()},submit);
    status(data.message||'Vérifie ta boîte e-mail.',false);
   }catch(e){status(e.message,true)}
  };
  fetch('/auth/password/status',{cache:'no-store'}).then(function(r){return r.json()})
   .then(function(data){if(!data.email_reset_available){
     submit.disabled=true;status('L’envoi des e-mails de récupération n’est pas encore activé sur TrekMap.',true);
   }}).catch(function(){status('Impossible de vérifier le service de récupération.',true)});
 }
 function openReset(token){
  if(!openTemplate('Choisir un nouveau mot de passe',
   '<p>Ton lien ne peut être utilisé qu’une fois et expire après 30 minutes.</p>'+
   '<label>Nouveau mot de passe (12 caractères minimum)<input id="tm-new-reset-password" type="password" minlength="12" maxlength="200" autocomplete="new-password" required></label>'+
   '<label>Confirmer le mot de passe<input id="tm-confirm-reset-password" type="password" minlength="12" autocomplete="new-password" required></label>'+
   '<div role="status" aria-live="polite" id="tm-recovery-status"></div>'+
   '<div class="tm-recovery-actions"><button type="button" id="tm-recovery-back">Retour</button>'+
   '<button type="button" class="primary" id="tm-recovery-apply">Changer mon mot de passe</button></div>'))return;
  $('tm-recovery-back').onclick=function(){authModal('login')};
  var send=$('tm-recovery-apply');
  send.onclick=async function(){
   var pass=$('tm-new-reset-password'),confirm=$('tm-confirm-reset-password');
   if(!pass.reportValidity()||!confirm.reportValidity())return;
   if(pass.value!==confirm.value){status('Les mots de passe ne correspondent pas.',true);return}
   status('Réinitialisation…',false);
   try{
    var data=await post('reset',{token:token,new_password:pass.value},send);
    pass.value='';confirm.value='';
    send.disabled=true;
    status(data.message||'Mot de passe modifié. Reconnecte-toi.',false);
    window.localStorage?.removeItem('trekmap_token');
    window.localStorage?.removeItem('trekmap_user');
   }catch(e){status(e.message,true)}
  };
 }
 function injectForgot(){
  if(!$('auth-login')||!$('auth-pass')||!$('switch-auth')||$('tm-forgot-link'))return;
  var target=$('auth-msg');
  if(!target)return;
  var button=document.createElement('button');
  button.type='button';button.id='tm-forgot-link';
  button.textContent='Mot de passe oublié ?';
  target.after(button);
  button.onclick=openForgot;
 }
 var scheduled=false;
 new MutationObserver(function(){
  if(scheduled)return;scheduled=true;
  queueMicrotask(function(){scheduled=false;injectForgot()});
 }).observe(modal,{childList:true,subtree:true});
 injectForgot();
 var match=window.location.hash.match(/^#reset=([A-Za-z0-9_-]{40,160})$/);
 if(match){
  var token=match[1];
  try{window.history.replaceState(null,'',window.location.pathname+window.location.search)}catch(_){}
  setTimeout(function(){openReset(token)},0);
 }
 window.TrekMapRecoveryUI={openForgot:openForgot,openReset:openReset};
})();
</script>
<!-- TM_FINISH_RECOVERY_END -->'''
if html.count('</body>')!=1:raise SystemExit('Frontend: body closing marker invalid')
path.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
print('Accueil/TrekBrain finish and secure password recovery UI installed')
