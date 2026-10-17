"""TrekMap: navigation par espaces et révélation progressive des outils.

Couche additive, construite après la chaîne UI existante.
Ne modifie ni les données, ni TrekBrain, ni les handlers GPS et hors ligne.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "frontend" / "index.html"
HIKE = ROOT / "frontend" / "hike.html"
START = "<!-- TREKMAP_FOUR_SPACES_START -->"
END = "<!-- TREKMAP_FOUR_SPACES_END -->"
html = INDEX.read_text(encoding="utf-8")
html = re.sub(r"\s*<!-- TREKMAP_FOUR_SPACES_START -->.*?<!-- TREKMAP_FOUR_SPACES_END -->\s*", "\n", html, flags=re.S)
for marker in ("TREKMAP_PROFILE_V2_START", "TREKMAP_INLINE_FILTERS_2026_START", "TM_HIKER_NAV_ENTRY_START"):
    if marker not in html:
        raise SystemExit("Navigation par espaces: prérequis absent: " + marker)

block = r'''<!-- TREKMAP_FOUR_SPACES_START -->
<style id="tm-four-spaces-css">
/* L'écran principal est une carte, pas un catalogue de boutons. */
:root{--tm-space-line:#dbe8df;--tm-space-green:#145b3d;--tm-space-soft:#f5f9f6}
#tm-primary-navigation{display:flex;gap:5px;align-items:center;justify-content:flex-end;min-width:0}
#tm-primary-navigation .tm-space-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;
 border:1px solid transparent;border-radius:11px;min-height:44px;padding:0 11px;
 background:transparent;color:#eaf7ee;white-space:nowrap;font-size:13px;font-weight:760}
#tm-primary-navigation .tm-space-button[aria-current="page"],#tm-primary-navigation .tm-space-button:hover{
 background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.20);color:#fff}
#tm-primary-navigation .tm-space-icon{font-size:18px;font-weight:500;line-height:1}
#tm-top-actions{display:none!important} /* Conservé en DOM comme adaptateur fonctionnel. */
#tm-unified-topbar{grid-template-columns:minmax(158px,234px) minmax(200px,1fr) auto!important;gap:15px!important}
#tm-primary-navigation .tm-space-button:focus-visible,.tm-design-action:focus-visible,
#tm-design-filter-flyout :is(select,button):focus-visible{outline:3px solid #fac75a!important;outline-offset:2px}
#tm-mobile-nav .tm-mobile-nav-btn[data-tm-space]{min-width:0;flex:1;border:0;background:transparent;
 color:#597266;font-size:11px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
#tm-mobile-nav .tm-mobile-nav-btn[data-tm-space][aria-current="page"]{background:#e7f4ec!important;color:#0e6543!important}
#tm-mobile-nav .tm-mobile-nav-btn[data-tm-space] .tm-m-icon{font-size:20px;line-height:1.15}
#tm-design-filter-flyout{position:fixed;z-index:9001;display:none;width:min(286px,calc(100vw - 20px));
 border:1px solid var(--tm-space-line);border-radius:16px;padding:14px;background:#fff;
 box-shadow:0 18px 42px rgba(10,39,26,.22);color:#244333}
#tm-design-filter-flyout.open{display:block}
#tm-design-filter-flyout label{display:block;font-size:13px;font-weight:800;margin:0 0 8px}
#tm-design-filter-flyout select{width:100%;min-height:46px;padding:9px;border:1px solid #a6ccb6;
 border-radius:10px;background:#fff;color:#124f37}
#tm-design-filter-flyout .tm-flyout-foot{display:flex;justify-content:flex-end;margin-top:9px}
#tm-design-filter-flyout button{min-height:38px;border:0;background:#e6f3ea;color:#16583a;
 border-radius:10px;padding:7px 12px;font-weight:750}
#tm-inline-filters{gap:7px!important}
#tm-design-toolbar{position:absolute;z-index:3650;top:calc(var(--tm-top) + 69px);right:clamp(276px,21vw,340px);display:flex;align-items:center;gap:6px}
body.tm-map-immersive #tm-design-toolbar{display:none!important}
#tm-design-add-menu{position:absolute;top:50px;right:0;display:none;min-width:200px;padding:7px;background:#fff;border:1px solid #d6e6da;border-radius:14px;box-shadow:0 15px 40px rgba(9,45,26,.20)}
#tm-design-add-menu.is-open{display:flex;flex-direction:column;gap:4px}
#tm-design-add-menu button{min-height:44px;padding:9px 12px;border:0;border-radius:9px;background:#f4f8f5;color:#16482f;font-weight:760;text-align:left}
#tm-design-add-menu button:hover{background:#e8f4ec}

#tm-inline-filters select{min-width:126px!important}
#tm-inline-filters [data-filter-target="duration-filter"]{max-width:152px!important}
#tm-design-toolbar #tm-design-filter-button,#tm-design-toolbar #tm-design-add-button{
 display:inline-flex!important;align-items:center;justify-content:center;gap:5px;
 min-height:44px!important;border-radius:12px!important;background:#fff!important;
 color:#154b32!important;border:1px solid #d3e3d9!important;font-size:12px!important;font-weight:800!important}
.map-tools .tm-design-map-actions{display:flex;gap:6px;margin:8px 0 0;border-top:1px solid #e4ede6;padding-top:9px;flex-direction:column}
.map-tools .tm-design-map-actions button{min-height:43px;text-align:left}
#tm-desktop-info{pointer-events:auto}
.tm-trek-tile,.tm-p-item{transition:border-color .14s,box-shadow .14s}
.tm-trek-tile{border-radius:16px!important}
#tm-profile-v2 .tm-p-nav{gap:5px}
body.tm-design-library-mode #tm-profile-v2 [data-p-tab="home"],
body.tm-design-library-mode #tm-profile-v2 [data-p-tab="preferences"]{display:none!important}
body.tm-design-library-mode #tm-profile-v2 .tm-p-brand:after{content:"MES TREKS";display:block;font-size:10px;letter-spacing:.12em;color:#a8d2b6}
#tm-design-library-hint{display:none}
body.tm-design-library-mode #tm-design-library-hint{display:block;color:#d8ebe0;font-size:11px;padding:9px 12px}
@media(min-width:821px) and (max-width:1160px){
 #tm-primary-navigation .tm-space-label{font-size:11px}
 #tm-primary-navigation .tm-space-button{padding:0 7px;gap:4px}
 #tm-unified-topbar{grid-template-columns:150px minmax(180px,1fr) auto!important;gap:9px!important}
}
@media(min-width:821px) and (max-width:950px){
 #tm-primary-navigation .tm-space-label{display:none}
 #tm-primary-navigation .tm-space-button{width:43px}
}
@media(max-width:820px){
 #tm-unified-topbar{grid-template-columns:42px minmax(0,1fr)!important;gap:9px!important}
 #tm-primary-navigation{display:none!important}
 #tm-mobile-nav{display:flex!important;justify-content:space-around;align-items:center;padding-inline:5px!important}
 #tm-mobile-nav .tm-mobile-nav-btn[data-tm-space]{min-height:50px!important;border-radius:12px!important}
 #tm-mobile-nav .tm-mobile-nav-btn[data-tm-space] .tm-space-label{white-space:nowrap;font-size:10px}
 #tm-inline-filters{display:none!important}
 #tm-design-toolbar{top:calc(var(--tm-top) + 10px);right:12px}
 #tm-design-toolbar #tm-design-filter-button,#tm-design-toolbar #tm-design-add-button{padding:8px 11px!important}
 #tm-desktop-info{display:none!important}
 body.tm-brain-route-mode #tm-design-toolbar{display:none!important}
 #tm-unified-drawer .tm-trek-tile{min-width:235px}
}
@media(max-width:380px){
 #tm-mobile-nav .tm-mobile-nav-btn[data-tm-space] .tm-space-label{font-size:9px}
 #tm-design-toolbar #tm-design-filter-button,#tm-design-toolbar #tm-design-add-button{font-size:11px!important}
}
@media(prefers-reduced-motion:reduce){
 .tm-trek-tile,.tm-p-item{transition:none!important}
}
</style>
<script id="tm-four-spaces-js">
(function(){
 'use strict';
 if(window.TrekMapFourSpaces)return;
 var $=function(id){return document.getElementById(id)};
 var top=$('tm-unified-topbar'),app=$('app'),mobileNav=$('tm-mobile-nav');
 if(!top||!app||!mobileNav)return;
 var spaces=[
  ['explore','⌖','Explorer'],
  ['brain','✦','TrekBrain'],
  ['library','▣','Mes treks'],
  ['profile','♙','Profil']
 ];
 var current='explore',profile=$('tm-profile-v2');
 function mobile(){return window.innerWidth<=820}
 function profileOpen(){return !!(profile&&!profile.hidden)}
 function activate(space){
  current=space;
  document.querySelectorAll('[data-tm-space]').forEach(function(b){
   var active=b.dataset.tmSpace===space;
   b.setAttribute('aria-current',active?'page':'false');
   b.classList.toggle('active',active);
  });
 }
 function makeButton(space,icon,label,isMobile){
  var b=document.createElement('button');
  b.type='button';
  b.dataset.tmSpace=space;
  b.className=isMobile?'tm-mobile-nav-btn tm-space-button':'tm-space-button';
  b.setAttribute('aria-label',label);
  b.innerHTML='<span class="'+(isMobile?'tm-m-icon':'tm-space-icon')+'" aria-hidden="true">'+icon+
   '</span><span class="tm-space-label">'+label+'</span>';
  return b;
 }
 var topNav=document.createElement('nav');
 topNav.id='tm-primary-navigation';
 topNav.setAttribute('aria-label','Espaces de TrekMap');
 spaces.forEach(function(t){topNav.appendChild(makeButton(t[0],t[1],t[2],false))});
 top.appendChild(topNav);
 mobileNav.replaceChildren();
 spaces.forEach(function(t){mobileNav.appendChild(makeButton(t[0],t[1],t[2],true))});
 function hideHome(){try{window.TrekMapHideHome&&window.TrekMapHideHome()}catch(_){}}
 function closeFilters(){
  document.body.classList.remove('tm-inline-filters-open','tm-mobile-filters-open');
  $('tm-inline-advanced')?.setAttribute('aria-expanded','false');
 }
 function closeAdd(){
  var sheet=$('tm-mobile-create-sheet');
  sheet?.classList.remove('open');
  sheet?.setAttribute('aria-hidden','true');
 }
 function leaveProfile(){
  if(profileOpen())window.TrekMapProfileV2?.close?.();
  document.body.classList.remove('tm-design-library-mode');
 }
 function explore(){
  leaveProfile();closeAdd();closeFilters();
  hideHome();
  try{window.TrekBrainMapWorkspace?.exit?.()}catch(_){}
  var tab=document.querySelector('.tab[data-tab="all"]');
  if(tab)tab.click();
  $('tm-unified-drawer')?.classList.remove('collapsed');
  activate('explore');
  try{window.map?.invalidateSize?.()}catch(_){}
 }
 function brain(){
  leaveProfile();closeFilters();closeAdd();hideHome();
  if(typeof window.TrekMapOpenAI==='function')window.TrekMapOpenAI();
  else $('tm-ai-launch')?.click();
  activate('brain');
 }
 async function openPrivateTab(tab){
  closeFilters();closeAdd();hideHome();
  try{window.TrekBrainMapWorkspace?.exit?.()}catch(_){}
  if(typeof currentUser!=='undefined'&&!currentUser){
   $('tm-account-btn')?.click();
   activate('explore');
   return;
  }
  if(!window.TrekMapProfileV2?.open){$('tm-account-btn')?.click();return}
  var library=tab!=='home';
  document.body.classList.toggle('tm-design-library-mode',library);
  activate(library?'library':'profile');
  await window.TrekMapProfileV2.open();
  profile?.querySelector('[data-p-tab="'+tab+'"]')?.click();
 }
 function openSpace(space){
  if(space==='explore')explore();
  else if(space==='brain')brain();
  else if(space==='library')openPrivateTab('projects');
  else if(space==='profile')openPrivateTab('home');
 }
 function onNavClick(e){
  var b=e.target.closest('[data-tm-space]');
  if(!b)return;
  e.preventDefault();
  openSpace(b.dataset.tmSpace);
 }
 topNav.addEventListener('click',onNavClick);
 mobileNav.addEventListener('click',onNavClick);
 activate('explore');
 // Quitter le profil remet l'espace Explorer au premier plan, sans toucher aux données.
 profile?.querySelector('#tm-p-exit')?.addEventListener('click',function(){
  document.body.classList.remove('tm-design-library-mode');
  activate('explore');
 });
 if(profile){
  new MutationObserver(function(){
   if(profile.hidden&&['profile','library'].includes(current)){
    document.body.classList.remove('tm-design-library-mode');
    activate('explore');
   }
  }).observe(profile,{attributes:true,attributeFilter:['hidden']});
 }
 var profileNav=profile?.querySelector('.tm-p-nav');
 if(profileNav){
  var hint=document.createElement('span');hint.id='tm-design-library-hint';
  hint.textContent='Aventures · Collections · Hors ligne · Carnet';
  profileNav.insertBefore(hint,profileNav.firstChild.nextSibling);
 }
 // Les vrais boutons créer/importer restent en DOM, pour préserver leurs handlers.
 var tools=document.querySelector('.map-tools');
 if(tools){
  var toolbar=document.createElement('div');
  toolbar.id='tm-design-toolbar';
  toolbar.setAttribute('role','group');
  toolbar.setAttribute('aria-label','Actions Explorer');
  app.appendChild(toolbar);
  var panel=$('tm-map-options-panel');
  if(panel&&!panel.querySelector('.tm-design-map-actions')){
   var actionGroup=document.createElement('div');
   actionGroup.className='tm-design-map-actions';
   [['＋ Tracer un trek','tm-create-btn'],['⇧ Importer un GPX','tm-import-btn']].forEach(function(pair){
    var b=document.createElement('button');b.type='button';b.textContent=pair[0];
    b.addEventListener('click',function(){
     panel.classList.remove('tm-show');
     $('tm-map-options')?.setAttribute('aria-expanded','false');
     $(pair[1])?.click();
    });
    actionGroup.appendChild(b);
   });
   panel.appendChild(actionGroup);
  }
  function actionButton(id,label){
   var b=document.createElement('button');
   b.type='button';b.id=id;b.textContent=label;b.className='tm-design-action';
   toolbar.appendChild(b);
   return b;
  }
  var addButton=actionButton('tm-design-add-button','＋ Ajouter');
  var filtersButton=actionButton('tm-design-filter-button','☷ Filtres');
  var addMenu=document.createElement('div');
  addMenu.id='tm-design-add-menu';
  addMenu.setAttribute('role','group');
  addMenu.setAttribute('aria-label','Ajouter un trek');
  [['✎ Tracer un trek','tm-create-btn'],['⇧ Importer un GPX','tm-import-btn']].forEach(function(pair){
   var b=document.createElement('button');b.type='button';b.textContent=pair[0];
   b.addEventListener('click',function(){addMenu.classList.remove('is-open');addButton.setAttribute('aria-expanded','false');$(pair[1])?.click()});
   addMenu.appendChild(b);
  });
  toolbar.appendChild(addMenu);
  addButton.setAttribute('aria-expanded','false');
  addButton.addEventListener('click',function(){
   if(mobile()){
    var sheet=$('tm-mobile-create-sheet');
    if(sheet){
     closeFilters();sheet.classList.add('open');
     sheet.setAttribute('aria-hidden','false');return;
    }
   }
   var open=!addMenu.classList.contains('is-open');
   addMenu.classList.toggle('is-open',open);
   addButton.setAttribute('aria-expanded',String(open));
  });
  document.addEventListener('pointerdown',function(e){
   if(!toolbar.contains(e.target)){addMenu.classList.remove('is-open');addButton.setAttribute('aria-expanded','false')}
  },true);
  document.addEventListener('keydown',function(e){
   if(e.key==='Escape'&&addMenu.classList.contains('is-open')){addMenu.classList.remove('is-open');addButton.setAttribute('aria-expanded','false');addButton.focus()}
  });
  filtersButton.addEventListener('click',function(){
   if(mobile()){
    closeAdd();
    var section=document.querySelector('#sidebar .filters');
    section?.classList.remove('tm-collapsed');
    document.body.classList.remove('tm-filters-collapsed');
    document.body.classList.toggle('tm-mobile-filters-open');
    $('tm-unified-drawer')?.classList.add('collapsed');
   }else $('tm-inline-advanced')?.click();
  });
 }
 // Les filtres Distance, Dénivelé et Durée réutilisent les trois popovers natifs,
 // déjà testés avec de vrais navigateurs et liés aux valeurs des filtres source.
 // Synchronisation visuelle minimale des espaces, sans polling ni requêtes.
 document.addEventListener('click',function(e){
  if(e.target.closest('#tm-ai-launch'))activate('brain');
  if(e.target.closest('#tm-p-exit'))activate('explore');
  if(e.target.closest('#tm-brand'))activate('explore');
 },true);
 var aiPanel=$('tm-ai-overlay');
 if(aiPanel)new MutationObserver(function(){
  if(aiPanel.classList.contains('open'))activate('brain');
 }).observe(aiPanel,{attributes:true,attributeFilter:['class']});
 new MutationObserver(function(){
  if(document.body.classList.contains('tm-brain-route-mode'))activate('brain');
 }).observe(document.body,{attributes:true,attributeFilter:['class']});
 window.TrekMapFourSpaces={
  open:openSpace,getActive:function(){return current},
  openDuration:function(){document.querySelector('[data-filter-target="duration-filter"]')?.click()},
  showLibrary:function(tab){return openPrivateTab(['projects','collections','downloads','journal'].includes(tab)?tab:'projects')}
 };
})();
</script>
<!-- TREKMAP_FOUR_SPACES_END -->'''
if html.count("</body>") != 1:
    raise SystemExit("Navigation par espaces: fermeture de body ambiguë")
INDEX.write_text(html.replace("</body>", block + "\n</body>", 1), encoding="utf-8")

# La randonnée reste son propre écran : appliquer seulement une simplification
# visuelle additive, sans remplacer ses actions GPS, sa carte ni ses contrôles.
HSTART = "<!-- TREKMAP_HIKE_DESIGN_START -->"
HEND = "<!-- TREKMAP_HIKE_DESIGN_END -->"
hike = HIKE.read_text(encoding="utf-8")
hike = re.sub(r"\s*<!-- TREKMAP_HIKE_DESIGN_START -->.*?<!-- TREKMAP_HIKE_DESIGN_END -->\s*", "\n", hike, flags=re.S)
hike_block = r'''<!-- TREKMAP_HIKE_DESIGN_START -->
<style id="tm-hike-design">
header{background:#104f37;box-shadow:0 5px 20px rgba(10,45,27,.13)}
header #back{font-weight:760}
#mapwrap{background:#e1eee4}
#gps-hud{border-radius:18px;border-color:#cfe4d5}
#gps-hud-actions button{border-radius:13px}
#hike-options .option-group{box-shadow:0 3px 14px rgba(13,54,29,.05)}
#hike-options .option-group summary{font-size:14px;letter-spacing:.01em}
@media(max-width:850px){
 header #center{display:none!important}
 #mapwrap{height:clamp(410px,calc(100dvh - 128px),840px)}
 #gps-map-controls{right:13px;top:12px}
 #gps-map-controls button{border-radius:14px!important}
 #gps-hud{left:10px;right:10px;bottom:11px}
 #hike-options{border-radius:22px 22px 0 0!important}
}
</style>
<!-- TREKMAP_HIKE_DESIGN_END -->'''
if hike.count("</body>") != 1:
    raise SystemExit("Mode randonnée: fermeture de body ambiguë")
HIKE.write_text(hike.replace("</body>", hike_block + "\n</body>", 1), encoding="utf-8")
print("Design TrekMap: navigation en 4 espaces, outils contextuels et mode randonnée installés")

# Dernière couche : organiser les fiches et la bibliothèque sans recréer de contrôles.
from runpy import run_path
run_path(str(Path(__file__).with_name('apply_detail_profile_polish.py')))
