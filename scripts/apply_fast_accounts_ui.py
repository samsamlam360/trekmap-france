"""Launch Explorer directly and expose safe multi-account switching.

The app never stores account passwords or session bearer tokens in JS.
Quick switches use a server-side, HttpOnly cookie grant after login.
"""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
p=root/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
start="<!-- TM_FAST_ACCOUNTS_START -->"
end="<!-- TM_FAST_ACCOUNTS_END -->"
html=re.sub(r"\s*<!-- TM_FAST_ACCOUNTS_START -->.*?<!-- TM_FAST_ACCOUNTS_END -->\s*","\n",html,flags=re.S)
if "TM_FINISH_RECOVERY_START" not in html:raise SystemExit("Recovery UI must be installed before fast accounts")
block=r'''<!-- TM_FAST_ACCOUNTS_START -->
<style id="tm-fast-accounts-css">
#tm-switch-accounts{display:flex;align-items:center;gap:9px;justify-content:flex-start;
 min-height:47px;cursor:pointer}
#tm-accounts-modal{display:grid;gap:13px;min-width:0}
#tm-accounts-modal p{color:#506a59;font-size:13px;line-height:1.6;margin:0}
#tm-accounts-list{display:grid;gap:9px}
.tm-accounts-row{border:1px solid #d5e7da;border-radius:13px;background:#fafdfb;
 padding:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.tm-accounts-avatar{width:42px;height:42px;background:#e4f2e9;color:#0d6042;
 border-radius:13px;display:grid;place-items:center;flex:none;font-size:21px;font-weight:900}
.tm-accounts-info{flex:1;min-width:125px}
.tm-accounts-info b{display:block;font-size:14px;color:#164c33}
.tm-accounts-info small{display:block;color:#60816c;overflow-wrap:anywhere}
.tm-accounts-row button{min-height:44px;border:1px solid #bdd9c8;border-radius:10px;
 font-size:12px;font-weight:790;color:#135b3c;background:#edf8f1;padding:8px 12px}
.tm-accounts-row button[disabled]{opacity:.65;cursor:default}
.tm-accounts-row .tm-accounts-remove{background:#fff;color:#9c4a43;border-color:#e5cbc7}
#tm-accounts-message{font-size:13px;color:#9b423d;min-height:18px}
#tm-accounts-actions{display:flex;flex-wrap:wrap;gap:10px}
#tm-accounts-actions button{min-height:47px;padding:10px 16px;border-radius:11px;
 border:1px solid #aacdb7;background:#f3faf5;color:#146344;font-size:13px;font-weight:850}
#tm-accounts-actions #tm-accounts-add{background:#11754e;color:#fff;border-color:#11754e}
#tm-profile-v2 #tm-switch-accounts:focus-visible,
#tm-accounts-modal :is(button,a):focus-visible{outline:3px solid #e9b94f!important;outline-offset:2px}
@media(max-width:780px){#tm-accounts-actions button{flex:1 1 120px}.tm-accounts-row{padding:10px}}
</style>
<script id="tm-fast-accounts-js">
(function(){
 'use strict';
 if(window.TrekMapAccounts)return;
 var $=function(id){return document.getElementById(id)};
 var profile=$('tm-profile-v2');
 function menuButton(){
  var nav=profile?.querySelector('.tm-p-nav');
  if(!nav||$('tm-switch-accounts'))return;
  var b=document.createElement('button');b.type='button';b.id='tm-switch-accounts';
  b.textContent='⇄ Changer de compte';b.setAttribute('aria-label','Gérer mes comptes connectés');
  var exit=$('tm-p-exit');if(exit)exit.before(b);else nav.appendChild(b);
  b.addEventListener('click',openAccounts);
 }
 function headersFor(method){return typeof headers==='function'?headers({'Content-Type':'application/json'},method):{'Content-Type':'application/json'}}
 async function json(path,method,data){
  var opts={method:method||'GET',credentials:'same-origin',cache:'no-store',
   headers:headersFor(method||'GET')};
  if(data!==undefined)opts.body=JSON.stringify(data);
  var response=await fetch(path,opts);
  var payload=await response.json().catch(function(){return {}});
  if(!response.ok)throw Error(payload.detail||'Opération impossible.');
  return payload;
 }
 function notice(message){var el=$('tm-accounts-message');if(el)el.textContent=message||''}
 function renderAccounts(data){
  var list=$('tm-accounts-list');if(!list)return;
  list.replaceChildren();
  var accounts=Array.isArray(data.accounts)?data.accounts:[];
  if(!accounts.length){var p=document.createElement('p');p.textContent='Aucun compte enregistré sur cet appareil.';list.appendChild(p)}
  accounts.forEach(function(account){
   var row=document.createElement('div');row.className='tm-accounts-row';
   var avatar=document.createElement('span');avatar.className='tm-accounts-avatar';
   avatar.textContent=(account.username||'?').charAt(0).toUpperCase();
   var info=document.createElement('div');info.className='tm-accounts-info';
   var name=document.createElement('b');name.textContent=account.username||'Compte';
   var email=document.createElement('small');email.textContent=account.email||'';
   info.append(name,email);row.append(avatar,info);
   var switchButton=document.createElement('button');switchButton.type='button';
   switchButton.textContent=account.active?'Compte actif':'Utiliser ce compte';
   switchButton.disabled=!!account.active;row.appendChild(switchButton);
   switchButton.addEventListener('click',async function(){
    switchButton.disabled=true;notice('Changement de compte…');
    try{
     await json('/auth/accounts/switch','POST',{user_id:Number(account.id)});
     try{localStorage.removeItem('trekmap_token');localStorage.removeItem('trekmap_user')}catch(_){}
     // Clear every previous profile and map cache in memory: no account data leak.
     window.location.reload();
    }catch(e){switchButton.disabled=false;notice(e.message)}
   });
   if(!account.active){
    var remove=document.createElement('button');remove.type='button';
    remove.className='tm-accounts-remove';remove.textContent='Retirer';
    remove.addEventListener('click',async function(){
     remove.disabled=true;
     try{await json('/auth/accounts/remove','POST',{user_id:Number(account.id)});
      row.remove();notice('Compte retiré de cet appareil.')}
     catch(e){remove.disabled=false;notice(e.message)}
    });
    row.appendChild(remove);
   }
   list.appendChild(row);
  });
  var add=$('tm-accounts-add');
  if(add)add.disabled=accounts.length>=Number(data.max_accounts||5);
 }
 async function openAccounts(){
  try{if(typeof currentUser!=='undefined'&&!currentUser){authModal('login');return}}
  catch(_){}
  window.TrekMapProfileV2?.close?.();
  if(typeof openModal!=='function')return;
  openModal('<div class="modal-head"><h2>Mes comptes</h2><button class="close" id="modal-close" aria-label="Fermer">✕</button></div>'+
   '<div id="tm-accounts-modal"><p>Connecte chaque compte une fois avec son mot de passe. Tu pourras ensuite changer de compte sur cet appareil sans le ressaisir. Sur un appareil partagé, déconnecte-toi pour effacer les comptes mémorisés.</p>'+
   '<div id="tm-accounts-list"><p>Chargement des comptes…</p></div>'+
   '<div id="tm-accounts-message" role="status" aria-live="polite"></div>'+
   '<div id="tm-accounts-actions"><button id="tm-accounts-add" type="button">＋ Ajouter un compte</button>'+
   '<button id="tm-accounts-close" type="button">Terminer</button></div></div>');
  $('modal-close').onclick=closeModal;
  $('tm-accounts-close').onclick=closeModal;
  $('tm-accounts-add').onclick=function(){authModal('login')};
  try{
   // Explicitly enroll the already logged-in account, including older sessions.
   await json('/auth/accounts/enroll','POST',{});
   var result=await json('/auth/accounts','GET');
   renderAccounts(result);
  }catch(e){notice(e.message)}
 }
 menuButton();
 window.TrekMapAccounts={open:openAccounts};
 // Direct launch: open the map as soon as the first lightweight catalog is ready.
 function showExplorerAutomatically(){
  window.TrekMapHideHome?.();
  var map=document.getElementById('map');
  if(map)map.setAttribute('aria-label','Carte des treks, chargée au démarrage');
 }
 if(window.allTreks?.length)showExplorerAutomatically();
 else document.addEventListener('trekmap:catalog-ready',showExplorerAutomatically,{once:true});
})();
</script>
<!-- TM_FAST_ACCOUNTS_END -->'''
if html.count("</body>")!=1:raise SystemExit("Malformed body")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Direct map launch and multi-account selector installed")
