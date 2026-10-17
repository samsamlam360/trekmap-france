"""TrekMap : fiches de randonnée et bibliothèque personnelle plus lisibles.

Installé en dernier, après les quatre espaces. Les contrôles réels et leurs
gestionnaires restent les mêmes ; aucune route, base ou donnée n'est modifiée.
"""
from pathlib import Path
import re

root=Path(__file__).resolve().parents[1]
p=root/'frontend'/'index.html'
html=p.read_text(encoding='utf-8')
html=re.sub(r'\s*<!-- TM_DETAIL_PROFILE_POLISH_START -->.*?<!-- TM_DETAIL_PROFILE_POLISH_END -->\s*','\n',html,flags=re.S)
for marker in ['TREKMAP_FOUR_SPACES_START','TREKMAP_PROFILE_V2_START','TM_HIKER_NAV_ENTRY_START']:
    if marker not in html:
        raise SystemExit('Polish UI: prérequis manquant : '+marker)

block=r'''<!-- TM_DETAIL_PROFILE_POLISH_START -->
<style id="tm-detail-profile-polish-css">
/* Une fiche : résumé > préparer/partir > itinéraire > informations > avis. */
#modal.tm-detail-refined{width:min(790px,calc(100vw - 18px))!important;max-width:790px!important;
  padding:clamp(15px,2.5vw,24px)!important;color:#173a2a}
#modal.tm-detail-refined .modal-head{display:flex;align-items:flex-start;gap:12px;margin-bottom:13px;
  padding-bottom:14px;border-bottom:1px solid #deebe1}
#modal.tm-detail-refined .modal-head h2{font-size:clamp(21px,2.6vw,30px)!important;
  line-height:1.16;letter-spacing:-.025em;margin:0 0 6px;color:#124d33}
#modal.tm-detail-refined .modal-head .close{flex:none;min-width:44px;min-height:44px;
  border-radius:12px!important}
#modal.tm-detail-refined .badges{display:flex;gap:7px;margin-bottom:13px;flex-wrap:wrap}
#modal.tm-detail-refined .tm-detail-overview{padding:0 0 8px}
#modal.tm-detail-refined .tm-detail-overview h3,
#modal.tm-detail-refined .tm-detail-extra h3{font-size:15px;font-weight:850;color:#174c33;margin:12px 0 10px}
#modal.tm-detail-refined .detail-grid{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));
  gap:8px!important;margin:0 0 15px!important}
#modal.tm-detail-refined .detail-grid .stat{border:1px solid #dce9e0;border-radius:13px;
  background:#f7faf7;padding:13px 10px!important;min-width:0;box-shadow:none}
#modal.tm-detail-refined .detail-grid .stat small{font-size:11px;color:#607869}
#modal.tm-detail-refined .detail-grid .stat b{font-size:17px;color:#144b33;overflow-wrap:anywhere}
#modal.tm-detail-refined .detail-desc{color:#465f51;font-size:14px;line-height:1.65;
  margin:10px 0 12px;white-space:pre-line}
#modal.tm-detail-refined .modal-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;
  position:relative;padding:14px 0;margin:3px 0 13px;border-block:1px solid #e1ebe4}
#modal.tm-detail-refined .modal-actions>button{flex:1 1 185px;min-height:46px;border-radius:11px;
  font-size:13px;font-weight:850}
#modal.tm-detail-refined .modal-actions>#plan-detail{background:#13764f;color:#fff}
#modal.tm-detail-refined .modal-actions>#hike-navigate-detail{background:#e7f5ed;color:#0b6040;
  border:1px solid #a8d1b8}
#modal.tm-detail-refined .tm-detail-secondary{flex:1 1 140px;min-width:142px;
  align-self:stretch;position:relative}
#modal.tm-detail-refined .tm-detail-secondary summary{min-height:46px;display:flex;align-items:center;
  justify-content:center;cursor:pointer;border:1px solid #bdd6c6;border-radius:11px;
  background:#f4f9f5;color:#15583a;font-size:13px;font-weight:850;list-style:none;padding:8px 12px}
#modal.tm-detail-refined .tm-detail-secondary summary::-webkit-details-marker{display:none}
#modal.tm-detail-refined .tm-detail-secondary summary:after{content:"⌄";margin-left:8px;font-size:17px}
#modal.tm-detail-refined .tm-detail-secondary[open] summary:after{content:"⌃"}
#modal.tm-detail-refined .tm-detail-secondary-buttons{display:grid;gap:5px;padding:9px;margin-top:6px;
 background:#fff;border:1px solid #d7e7db;border-radius:13px;
 box-shadow:0 12px 30px rgba(12,48,30,.11)}
#modal.tm-detail-refined .tm-detail-secondary-buttons button{width:100%;min-height:44px;
 text-align:left;border-radius:9px;font-size:13px;padding:10px 12px;white-space:normal}
#modal.tm-detail-refined .tm-detail-secondary-buttons .danger-btn{border-color:#eccccc;color:#a43f40}
#modal.tm-detail-refined #tm-hiker-detail{border:1px solid #d7e6da;border-radius:15px;
 padding:15px;margin:15px 0;background:#fbfdfb}
#modal.tm-detail-refined #tm-hiker-detail h3{color:#184c33;font-size:16px}
#modal.tm-detail-refined #tm-hiker-detail .tm-hiker-coords{overflow-wrap:anywhere}
#modal.tm-detail-refined .tm-detail-extra{border:1px solid #dce8df;background:#fff;border-radius:16px;
 padding:15px;margin:14px 0;overflow:hidden}
#modal.tm-detail-refined .tm-detail-extra .tm-detail-hero{border-radius:12px;overflow:hidden}
#modal.tm-detail-refined .tm-detail-extra .tm-gallery{max-width:100%;overflow-x:auto}
#modal.tm-detail-refined .comments{border-top:1px solid #e2eae4;padding-top:17px;margin-top:18px}
#modal.tm-detail-refined .comments h3{font-size:17px;color:#174b34}
#modal.tm-detail-refined .tm-detail-overview-kicker{color:#638171;font-size:11px;
 font-weight:850;letter-spacing:.09em;text-transform:uppercase}
#modal.tm-detail-refined :is(button,summary,input,textarea):focus-visible{outline:3px solid #ecb64e!important;outline-offset:2px}
#tm-profile-v2 .tm-p-nav{box-shadow:0 13px 30px rgba(6,52,30,.09)}
#tm-profile-v2 .tm-p-nav button.active{background:#e9f6ed;color:#11583c;border-color:transparent}
#tm-profile-v2 .tm-p-main{max-width:100%;min-width:0}
body.tm-design-library-mode #tm-profile-v2 .tm-p-hero{padding:17px 22px;min-height:90px}
body.tm-design-library-mode #tm-profile-v2 .tm-p-hero .tm-p-avatar{width:48px;height:48px;font-size:24px}
body.tm-design-library-mode #tm-profile-v2 .tm-p-hero p{font-size:12px}
#tm-profile-v2 .tm-p-content>.tm-p-inline:first-child{align-items:center}
#tm-profile-v2 .tm-p-cols>.tm-p-card{min-width:0}
#tm-profile-v2 .tm-p-project-row[hidden]{display:none!important}
#tm-profile-v2 #tm-p-status-filter{margin:0 0 13px;display:grid;gap:9px}
#tm-profile-v2 #tm-p-status-search{height:45px;padding:10px 13px;border-radius:11px;
 border:1px solid #bbd4c3;background:#fff;color:#18492f;font:inherit;font-size:14px}
#tm-profile-v2 .tm-p-status-chips{display:flex;gap:6px;flex-wrap:wrap}
#tm-profile-v2 .tm-p-status-chips button{border:1px solid #caddd0;min-height:39px;
 border-radius:50px;padding:8px 12px;color:#285b42;background:#f6faf7;font-size:12px;font-weight:800}
#tm-profile-v2 .tm-p-status-chips button[aria-pressed="true"]{background:#156b49;color:#fff;border-color:#156b49}
#tm-profile-v2 #tm-p-status-empty{padding:15px;font-size:13px;color:#60796a;
 border-radius:12px;background:#f7faf7;border:1px dashed #c8dacd}
#tm-profile-v2 .tm-p-more{border:1px solid #d6e6db;background:#fbfdfb;
 padding:0 13px 12px;border-radius:12px}
#tm-profile-v2 .tm-p-more>summary{cursor:pointer;display:flex;align-items:center;justify-content:space-between;
 padding:14px 4px;font-size:13px;font-weight:850;color:#15553a;min-height:44px;list-style:none}
#tm-profile-v2 .tm-p-more>summary::-webkit-details-marker{display:none}
#tm-profile-v2 .tm-p-more>summary:after{content:"⌄";font-size:20px}
#tm-profile-v2 .tm-p-more[open]>summary:after{content:"⌃"}
#tm-profile-v2 .tm-p-more-inner{display:grid;gap:12px;border-top:1px solid #e2ece5;padding-top:12px}
#tm-profile-v2 .tm-p-collection-tools{margin:10px 0;border:1px solid #d4e7d9;
 border-radius:11px;padding:0 12px;background:#fafdfb}
#tm-profile-v2 .tm-p-collection-tools summary{font-weight:850;cursor:pointer;padding:13px 0;color:#1d6847}
@media(max-width:780px){
 #modal.tm-detail-refined{padding:14px!important;max-height:calc(100dvh - 14px)}
 #modal.tm-detail-refined .detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
 #modal.tm-detail-refined .modal-actions>button{flex:1 1 100%;min-height:48px}
 #modal.tm-detail-refined .tm-detail-secondary{flex:1 1 100%}
 #tm-profile-v2 #tm-p-status-filter{gap:7px}
 #tm-profile-v2 .tm-p-status-chips{flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;
  padding-bottom:5px}
 #tm-profile-v2 .tm-p-status-chips button{flex:none;white-space:nowrap;min-height:44px}
 body.tm-design-library-mode #tm-profile-v2 .tm-p-hero{min-height:75px;padding:13px}
 body.tm-design-library-mode #tm-profile-v2 .tm-p-content{padding-top:12px}
}
@media(prefers-reduced-motion:reduce){#modal.tm-detail-refined *{transition:none!important}}
</style>
<script id="tm-detail-profile-polish-js">
(function(){
 'use strict';
 if(window.TrekMapDetailProfilePolish)return;
 var modal=document.getElementById('modal');
 var root=document.getElementById('tm-profile-v2');
 var content=root&&root.querySelector('#tm-p-content');
 if(!modal||!content)return;
 // Contrôles d'origine : tous les gestionnaires de clic restent attachés aux mêmes noeuds.
 function refineDetail(){
  var actions=modal.querySelector('.modal-actions'),grid=modal.querySelector('.detail-grid');
  if(!actions||!grid||!modal.querySelector('#fav-detail'))return;
  if(!modal.classList.contains('tm-detail-refined')){
   modal.classList.add('tm-detail-refined');
   var overview=document.createElement('section');
   overview.className='tm-detail-overview';
   var kicker=document.createElement('div');
   kicker.className='tm-detail-overview-kicker';kicker.textContent='En un coup d’œil';
   overview.appendChild(kicker);
   grid.before(overview);overview.appendChild(grid);
   var desc=modal.querySelector('.detail-desc');if(desc)overview.appendChild(desc);
   // Boutons principaux accessibles d'emblée ; fonctions secondaires dans un menu.
   var plan=actions.querySelector('#plan-detail');
   var hiking=actions.querySelector('#hike-navigate-detail');
   if(plan)actions.prepend(plan);
   if(hiking){if(plan)plan.after(hiking);else actions.prepend(hiking)}
   var more=document.createElement('details');
   more.className='tm-detail-secondary';
   var summary=document.createElement('summary');
   summary.textContent='Autres actions';
   var list=document.createElement('div');list.className='tm-detail-secondary-buttons';
   more.append(summary,list);actions.appendChild(more);
   if(!plan&&!hiking&&actions.querySelector('#export-detail')){
    actions.prepend(actions.querySelector('#export-detail'));
   }
  }
  var group=modal.querySelector('.tm-detail-secondary-buttons');
  if(group){
   Array.from(actions.children).forEach(function(node){
    if(node===group.parentElement ||node.id==='plan-detail'||node.id==='hike-navigate-detail'
       ||node.id==='export-detail'&&actions.querySelector('#export-detail')===node) return;
    if(node.tagName==='BUTTON')group.appendChild(node);
   });
   // L'édition des informations arrive après une requête réseau : regrouper aussi ce bouton.
  }
  var extra=modal.querySelector('.tm-detail-extra');
  if(extra&&!extra.querySelector('.tm-detail-polish-title')){
   var title=document.createElement('h3');title.className='tm-detail-polish-title';
   title.textContent='Photos, lieux et avis';extra.prepend(title);
  }
 }
 // Le contenu de la modale est souvent enrichi après ouverture par plusieurs modules.
 var scheduled=false;
 var observer=new MutationObserver(function(){
  if(scheduled)return;scheduled=true;
  queueMicrotask(function(){scheduled=false;refineDetail()});
 });
 observer.observe(modal,{childList:true,subtree:true});
 refineDetail();

 var state={status:'all',query:''};
 var statuses=[['all','Tous'],['planned','À découvrir'],['preparing','En préparation'],
  ['ready','Prêt'],['completed','Terminé']];
 function normalized(s){return String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()}
 function statusOf(row){
  var label=row.querySelector('[data-p-select]');
  var text=label?label.textContent:'';
  if(text.indexOf('En préparation')>=0)return 'preparing';
  if(text.indexOf('À découvrir')>=0)return 'planned';
  if(text.indexOf('Terminé')>=0)return 'completed';
  if(text.indexOf('Prêt')>=0)return 'ready';
  return 'planned';
 }
 function applyList(){
  var rows=Array.from(content.querySelectorAll('.tm-p-project-row'));
  var panel=content.querySelector('#tm-p-status-filter');
  if(!panel)return;
  var q=normalized(state.query.trim()),shown=0;
  rows.forEach(function(row){
   var ok=(state.status==='all'||statusOf(row)===state.status)
     &&(!q||normalized(row.textContent).includes(q));
   row.hidden=!ok;if(ok)shown++;
  });
  panel.querySelectorAll('[data-tm-status]').forEach(function(b){
   var filter=b.dataset.tmStatus;
   b.setAttribute('aria-pressed',String(state.status===filter));
   var count=filter==='all'?rows.length:rows.filter(function(r){return statusOf(r)===filter}).length;
   b.textContent=statuses.find(function(s){return s[0]===filter})[1]+' · '+count;
  });
  var empty=content.querySelector('#tm-p-status-empty');
  if(empty)empty.hidden=shown>0 ||rows.length===0;
 }
 function refineProfile(){
  var list=content.querySelector('.tm-p-project-row');
  if(list&&!content.querySelector('#tm-p-status-filter')){
   var parent=list.parentElement;
   if(parent){
    var filters=document.createElement('div');filters.id='tm-p-status-filter';
    var input=document.createElement('input');input.id='tm-p-status-search';input.type='search';
    input.autocomplete='off';input.placeholder='Rechercher dans mes treks…';
    input.setAttribute('aria-label','Rechercher dans mes treks');input.value=state.query;
    var chips=document.createElement('div');chips.className='tm-p-status-chips';
    chips.setAttribute('role','group');chips.setAttribute('aria-label','Filtrer les treks par état');
    statuses.forEach(function(item){
     var b=document.createElement('button');b.type='button';b.dataset.tmStatus=item[0];
     b.setAttribute('aria-pressed',String(state.status===item[0]));
     b.textContent=item[1];chips.appendChild(b);
    });
    filters.append(input,chips);parent.before(filters);
    var empty=document.createElement('p');empty.id='tm-p-status-empty';empty.hidden=true;
    empty.textContent='Aucun trek ne correspond à ces critères.';
    parent.after(empty);
    input.addEventListener('input',function(){state.query=input.value;applyList()});
    chips.addEventListener('click',function(e){
     var b=e.target.closest('[data-tm-status]');if(!b)return;
     state.status=b.dataset.tmStatus;applyList();
    });
   }
  }
  if(content.querySelector('#tm-p-status-filter'))applyList();
  // L'éditeur conserve le même formulaire, champs et sauvegarde.
  var form=content.querySelector('#tm-p-journey-form');
  if(form&&!form.querySelector('.tm-p-more')){
   var expandable=document.createElement('details');expandable.className='tm-p-more';
   var title=document.createElement('summary');title.textContent='Notes et photos personnelles';
   var inside=document.createElement('div');inside.className='tm-p-more-inner';
   expandable.append(title,inside);
   Array.from(form.children).forEach(function(child){
    if(child.matches('label')&&(child.querySelector('[name="notes"]')||
       child.querySelector('[name="local_photo"]')||child.querySelector('[name="remove_photo"]')||
       child.querySelector('[name="photos"]')) ||child.id==='tm-p-local-photo-preview'){
     inside.appendChild(child);
    }
   });
   var footer=form.querySelector('.tm-p-inline');
   if(footer)footer.before(expandable);else form.appendChild(expandable);
   // En cas de notes/photos déjà présentes, le contenu reste trouvable d'un clic.
  }
  var collection=content.querySelector('#tm-p-collection-content');
  if(collection&&!collection.querySelector('.tm-p-collection-tools')){
   var rename=collection.querySelector('[data-p-rename]');
   var deletion=collection.querySelector('[data-p-delete-collection]');
   if(rename&&deletion&&rename.parentElement===deletion.parentElement){
    var row=rename.parentElement;
    var tools=document.createElement('details');tools.className='tm-p-collection-tools';
    var summary=document.createElement('summary');summary.textContent='Gérer la collection';
    tools.appendChild(summary);row.before(tools);tools.appendChild(row);
   }
  }
 }
 var queue=false;
 var watch=new MutationObserver(function(){
  if(queue)return;queue=true;
  queueMicrotask(function(){queue=false;refineProfile()});
 });
 watch.observe(content,{childList:true,subtree:true});
 refineProfile();
 window.TrekMapDetailProfilePolish={refineDetail:refineDetail,refineProfile:refineProfile,
  setStatus:function(s){if(statuses.some(function(x){return x[0]===s})){state.status=s;applyList()}},
  getStatus:function(){return state.status}};
})();
</script>
<!-- TM_DETAIL_PROFILE_POLISH_END -->'''
if html.count('</body>')!=1:raise SystemExit('Polish UI: body ambigu')
p.write_text(html.replace('</body>',block+'\n</body>',1),encoding='utf-8')
print('TrekMap détail et profil : hiérarchie claire, filtres de statut et options regroupées')
