"""Cohesive TrekMap desktop/mobile ergonomics without replacing existing controls.

Run after apply_trekbrain_map_workspace.py. Presentation + accessibility helpers:
no routing, fetch, storage writes, endpoint changes or button replacement.
"""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_SITEWIDE_UX_START -->.*?<!-- TREKMAP_SITEWIDE_UX_END -->\s*",
    "\n", html, flags=re.S,
)
for marker in ("TREKMAP_UNIFIED_EXPERIENCE_START", "TREKMAP_MOBILE_EXPERIENCE_START",
               "TREKMAP_AI_EXPERIENCE_START", "TREKMAP_BRAIN_ROUTE_WORKSPACE_START"):
    if marker not in html:
        raise SystemExit("Sitewide UX prerequisite missing: " + marker)

block = r'''<!-- TREKMAP_SITEWIDE_UX_START -->
<style id="trekmap-sitewide-ux-css">
/* Research-led: NN/g recognition and progressive disclosure;
   Griffin et al. (2024) mobile-map cognitive load;
   W3C WCAG 2.2 focus and target sizes.
   All site functions remain in their original DOM. */
:root {
  --tm-ux-forest:#104630;
  --tm-ux-green:#116747;
  --tm-ux-accent:#0e704f;
  --tm-ux-text:#183529;
  --tm-ux-subtext:#526b5e;
  --tm-ux-line:#d8e6dc;
  --tm-ux-paper:#f6f9f6;
  --tm-ux-focus:#f2b83f;
  --tm-ux-shadow:0 12px 34px rgba(15,49,31,.13);
}
body,button,input,select,textarea { -webkit-font-smoothing:antialiased }
button,select,summary,[role="button"] { touch-action:manipulation }
button { transition:background-color .16s ease,color .16s ease,border-color .16s ease,box-shadow .16s ease }
button:disabled { cursor:not-allowed;opacity:.60 }
:is(button,a,input,textarea,select,summary,[role="button"],[tabindex]):focus-visible {
  outline:3px solid var(--tm-ux-focus)!important;
  outline-offset:3px!important;
  box-shadow:0 0 0 5px rgba(14,71,47,.2)!important;
}
:is(.tm-trek-tile,.tm-suggest,.tm-home-links button,.tm-home-login,#tm-main-search-clear,
    #tm-top-actions button,#tm-filter-toggle,#tm-drawer-head,#tm-map-options,
    #tm-map-options-panel button,#tm-mobile-nav button,#tm-ai-overlay button,
    .tm-brain-actions button,.modal button) { min-height:40px }
#tm-top-actions button,#tm-map-options-panel button,#tm-mobile-nav button,
.tm-home-login,.tm-hero-search button,.tm-ai-actions button { min-height:44px }
#tm-home { color:var(--tm-ux-text);scroll-behavior:smooth }
#tm-home .tm-home-nav { max-width:1280px;gap:18px }
#tm-home .tm-home-main { max-width:1280px }
#tm-home .tm-hero {
  min-height:min(600px,75dvh);
  gap:clamp(20px,4vw,70px);
}
#tm-home .tm-hero h1 { letter-spacing:-.052em;line-height:1.04;max-width:730px }
#tm-home .tm-hero-copy > p { max-width:610px;color:#486558;line-height:1.66 }
#tm-home .tm-kicker { letter-spacing:.12em }
#tm-home .tm-hero-search {
  border-color:#c3dccb;border-radius:18px;
  box-shadow:0 14px 35px rgba(14,65,42,.12);
}
#tm-home .tm-features article,#tm-home .tm-featured article,
#tm-home .tm-featured .tm-featured-card {
  border:1px solid var(--tm-ux-line);border-radius:18px;
  box-shadow:0 4px 18px rgba(20,66,43,.05);
}
#tm-home .tm-features small { font-size:13px;line-height:1.55;color:var(--tm-ux-subtext) }
#tm-home .tm-section-head { gap:16px }
#tm-home .tm-section-head h2 { line-height:1.18 }
#tm-unified-topbar {
  background:linear-gradient(115deg,#093c2a 0%,#0c573e 72%,#0d6145 100%)!important;
  border-bottom:1px solid rgba(255,255,255,.14);
}
/* Preserve five real topbar actions: a rigid search column used to overlap
   the TrekBrain button at 1440px, making a visible action unclickable. */
@media(min-width:1101px) {
  #tm-unified-topbar {
    grid-template-columns:235px minmax(250px,480px) minmax(0,1fr)!important;
    gap:12px!important;
  }
  #tm-top-actions { min-width:0!important;justify-content:flex-end!important }
  #tm-top-actions button { flex-shrink:1;min-width:44px }
}
@media(min-width:1101px) and (max-width:1320px) {
  #tm-unified-topbar { grid-template-columns:190px minmax(230px,420px) minmax(0,1fr)!important }
  #tm-top-actions button .label { display:none!important }
  #tm-top-actions button { width:44px!important;justify-content:center }
}
#tm-main-search-wrap { border:1px solid #d4e6da!important;border-radius:15px!important }
#tm-main-search { color:var(--tm-ux-text)!important }
#tm-main-search::placeholder { color:#526c5e;opacity:1 }
#tm-top-actions button { border-radius:12px!important }
#tm-unified-drawer .tm-drawer-shell {
  border:1px solid #c9ded1!important;
  box-shadow:var(--tm-ux-shadow)!important;
}
#tm-unified-drawer .tm-trek-tile {
  border-radius:13px!important;
  border-color:var(--tm-ux-line)!important;
  background:#fff;
}
#tm-unified-drawer .tm-trek-tile:hover {
  border-color:#75af8c!important;box-shadow:0 9px 22px rgba(12,74,42,.11)!important
}
#tm-unified-drawer .tm-trek-tile.selected {
  border-color:var(--tm-ux-accent)!important;
  box-shadow:0 0 0 2px rgba(17,103,71,.16)!important
}
#sidebar .filters { border:1px solid var(--tm-ux-line)!important }
#sidebar .filters .field label,#sidebar .filters .tm-criterion label {
  color:#405c4c!important;font-size:12px!important;line-height:1.4
}
#sidebar .filters :is(input:not([type="range"]),select) {
  border:1px solid #bdd2c4!important;border-radius:10px!important;
  min-height:40px;background:#fff;color:var(--tm-ux-text)
}
#sidebar .filters .tm-filter-section { color:var(--tm-ux-text) }
#tm-filter-toggle { border-radius:10px!important }
#tm-map-options { color:var(--tm-ux-text)!important }
#tm-map-options-panel { border-color:var(--tm-ux-line)!important }
.map-tools button:hover,#tm-map-options:hover { background:#eff8f1!important }
.leaflet-container { font-family:inherit }
.leaflet-popup-content-wrapper {
  border-radius:14px;box-shadow:0 14px 36px rgba(13,56,35,.18)
}
.modal,.tm-mobile-create-card {
  border:1px solid var(--tm-ux-line);
  border-radius:20px;box-shadow:0 25px 75px rgba(9,35,23,.18);
}
.modal { line-height:1.5 }
.modal .form-field label { font-size:13px;color:#345241 }
.modal :is(input:not([type="checkbox"]),select,textarea) {
  border-color:#bdd2c4;min-height:42px
}
.modal .modal-actions { flex-wrap:wrap;gap:10px }
.toast { max-width:min(420px,calc(100vw - 24px));line-height:1.45 }
#tm-ai-overlay .tm-ai-shell { box-shadow:0 24px 75px rgba(10,39,26,.23) }
#tm-ai-overlay .tm-ai-field label { color:#2b513d!important }
#tm-ai-overlay .tm-ai-field :is(input:not([type="checkbox"]),textarea,select) {
  border-radius:11px!important;min-height:42px
}
#tm-ai-overlay .tm-ai-empty,#tm-ai-overlay .tm-ai-progress { line-height:1.6 }
#tm-ai-overlay .tm-ai-section,#tm-ai-overlay .tm-ux-essentials {
  scroll-margin-block-start:18px
}
#tm-brain-route-panel .tm-brain-content { scrollbar-gutter:stable }
#tm-brain-route-panel .tm-brain-actions { gap:8px }
#tm-brain-route-panel .tm-brain-detail { line-height:1.54 }
#tm-brain-route-panel .tm-ux-adjust-day {
  display:inline-flex;align-items:center;justify-content:center;
  min-height:40px;margin:9px 0 3px;padding:7px 12px;
  border:1px solid #a9ceba;border-radius:10px;
  background:#eaf5ee;color:#14583b;font-size:12px;font-weight:800
}
#tm-brain-route-panel .tm-ux-adjust-day:hover { background:#dcefe3 }
@media(min-width:821px) and (max-width:1199px) {
  #tm-unified-topbar { gap:10px!important }
  #tm-top-actions button { padding-inline:10px!important }
  #tm-home .tm-hero { min-height:480px }
}
@media(max-width:820px) {
  html { scroll-padding-bottom:calc(85px + env(safe-area-inset-bottom,0px)) }
  #tm-home .tm-home-main { padding-inline:16px!important }
  #tm-home .tm-home-nav { padding-inline:16px!important }
  #tm-home .tm-hero { min-height:0!important;padding-top:26px!important }
  #tm-home .tm-hero h1 { font-size:clamp(36px,10.8vw,52px)!important;line-height:1.06 }
  #tm-home .tm-hero-copy > p { font-size:15px!important;line-height:1.55!important }
  #tm-home .tm-quick { flex-wrap:wrap;gap:10px 16px }
  #tm-home .tm-quick button { min-height:36px;padding:7px 2px }
  #tm-home .tm-features { gap:10px }
  #tm-home .tm-features article { padding:16px }
  #tm-home .tm-featured { gap:10px }
  #tm-home .tm-section-head { align-items:start;flex-wrap:wrap }
  #tm-main-search-wrap { border-radius:12px!important }
  #tm-main-search { font-size:16px!important }
  #tm-mobile-nav { border:1px solid #d1e4d7!important;border-radius:18px 18px 0 0!important }
  #tm-mobile-nav button { min-width:0;min-height:48px!important }
  #tm-unified-drawer .tm-drawer-shell { border-radius:18px!important }
  #tm-drawer-head { min-height:44px }
  #tm-brain-route-panel .tm-brain-content { scrollbar-gutter:auto }
  #tm-ai-overlay .tm-ai-field :is(input:not([type="checkbox"]),textarea,select) { font-size:16px!important }
  .modal-backdrop { padding:8px!important }
  .modal { max-height:calc(100dvh - 16px);padding:16px!important }
  .toast { left:12px!important;right:12px!important;width:auto }
}
@media(max-width:380px) {
  #tm-home .tm-hero-visual { max-height:230px!important }
  #tm-home .tm-map-orb { width:222px!important;height:222px!important }
  #tm-home .tm-floating-card { max-width:160px;padding:7px 9px;font-size:11px }
  #tm-home .tm-hero-search { gap:4px;padding:5px!important }
  #tm-home .tm-hero-search button { padding-inline:10px!important }
  .modal-actions button { flex:1;min-width:110px }
}
@media(prefers-reduced-motion:reduce) {
  *,*::before,*::after {
    animation-duration:.01ms!important;
    animation-iteration-count:1!important;
    transition-duration:.01ms!important;
    scroll-behavior:auto!important
  }
}
</style>
<script id="trekmap-sitewide-ux-js">
(function(){
  'use strict';
  /* Add semantics to existing buttons only: never clone controls or overwrite
     handlers, navigation, route requests, save/export, storage or the map. */
  var labels={
    'tm-brand':'Retour à l’accueil',
    'tm-main-search':'Rechercher des treks',
    'tm-filter-toggle':'Afficher ou replier les filtres',
    'tm-drawer-head':'Afficher ou replier les résultats de treks',
    'tm-map-options':'Options de la carte',
    'tm-ai-close':'Fermer la préparation TrekBrain',
    'tm-ai-generate':'Préparer l’itinéraire demandé',
    'tm-ai-save':'Enregistrer le trek proposé',
    'tm-ai-back':'Revenir aux critères de préparation',
    'tm-map-options-panel':'Options de la carte',
    'map-toggle':'Afficher la liste',
    'map-fit':'Recentrer la carte',
    'locate-map':'Afficher ma position',
    'tm-main-search-clear':'Effacer la recherche',
    'tm-ai-launch':'Ouvrir TrekBrain',
    'tm-import-btn':'Importer un fichier GPX',
    'tm-create-btn':'Créer un trek',
    'tm-favorites-btn':'Mes treks favoris',
    'tm-account-btn':'Mon compte'
  };
  function enhance(){
    Object.keys(labels).forEach(function(id){
      var el=document.getElementById(id);
      if(!el||(!el.matches('input,button,select,[role="button"]')))return;
      if(!el.hasAttribute('aria-label'))el.setAttribute('aria-label',labels[id]);
    });
    var search=document.getElementById('tm-main-search');
    if(search&&!search.hasAttribute('aria-controls'))search.setAttribute('aria-controls','tm-main-suggestions');
    var toast=document.getElementById('toast');
    if(toast){toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');toast.setAttribute('aria-atomic','true');}
    var dialog=document.getElementById('modal-backdrop');
    if(dialog)dialog.setAttribute('aria-label','Fenêtre TrekMap');
    document.querySelectorAll('#tm-unified-drawer .tm-trek-tile').forEach(function(card){
      if(!card.hasAttribute('aria-label')){
        var name=card.querySelector('strong');
        card.setAttribute('aria-label','Afficher le trek : '+(name?name.textContent.trim():'itinéraire'));
      }
    });
    document.querySelectorAll('.tm-home-links button,.tm-home-login').forEach(function(b){
      if(!b.hasAttribute('type'))b.setAttribute('type','button');
    });
    var mobile=document.getElementById('tm-mobile-nav');
    if(mobile&&!mobile.hasAttribute('aria-label'))mobile.setAttribute('aria-label','Navigation principale');
    // Every displayed day can return to the existing TrekBrain editing form.
    // The original route is untouched until the hiker deliberately regenerates.
    document.querySelectorAll('#tm-brain-route-panel .tm-brain-stage').forEach(function(stage,i){
      if(stage.querySelector('[data-tm-adjust-day]'))return;
      var b=document.createElement('button');
      b.type='button';
      b.className='tm-ux-adjust-day';
      b.setAttribute('data-tm-adjust-day',String(i+1));
      b.setAttribute('aria-label','Adapter les consignes de l’étape '+(i+1));
      b.textContent='✎ Ajuster cette étape';
      stage.appendChild(b);
    });
  }
  function sync(){
    var filters=document.querySelector('#sidebar .filters');
    var toggle=document.getElementById('tm-filter-toggle');
    if(filters&&toggle)toggle.setAttribute('aria-expanded',String(!filters.classList.contains('tm-collapsed')));
    var drawer=document.getElementById('tm-unified-drawer');
    var head=document.getElementById('tm-drawer-head');
    if(drawer&&head)head.setAttribute('aria-expanded',String(!drawer.classList.contains('collapsed')));
    var options=document.getElementById('tm-map-options-panel');
    var mapButton=document.getElementById('tm-map-options');
    if(options&&mapButton)mapButton.setAttribute('aria-expanded',String(options.classList.contains('tm-show')));
    document.querySelectorAll('#tm-mobile-nav [data-mobile-action]').forEach(function(b){
      if(b.classList.contains('active'))b.setAttribute('aria-current','page');
      else b.removeAttribute('aria-current');
    });
    document.querySelectorAll('.tab[data-tab]').forEach(function(b){
      b.setAttribute('aria-selected',String(b.classList.contains('active')));
    });
  }
  function init(){
    enhance();sync();
    var timer=0;
    var observer=new MutationObserver(function(mutations){
      if(!mutations.some(function(m){return m.addedNodes.length>0;}))return;
      if(timer)clearTimeout(timer);
      timer=setTimeout(function(){timer=0;enhance();sync();},70);
    });
    observer.observe(document.body,{childList:true,subtree:true});
    document.addEventListener('click',function(e){
      var t=e.target.closest&&e.target.closest('button,[role="button"]');
      if(!t)return;
      var day=t.getAttribute('data-tm-adjust-day');
      if(day&&window.TrekBrainMapWorkspace?.isActive?.()){
        // Activate the existing Modify action with its original, real plan.
        e.preventDefault();
        var panel=document.getElementById('tm-brain-route-panel');
        var modify=panel&&panel.querySelector('[data-workspace-action="modify"]');
        if(!modify)return;
        modify.click();
        var prompt=document.getElementById('tm-ai-prompt');
        if(prompt){
          var note='Réévalue prioritairement l’étape '+day+' et conserve autant que possible les autres journées.';
          if(!prompt.value.includes(note)){
            prompt.value=(prompt.value.trim()+'\n'+note).trim();
            prompt.dispatchEvent(new Event('input',{bubbles:true}));
          }
        }
      }
      setTimeout(sync,0);
    },true);
    document.addEventListener('keydown',function(e){
      if(e.key!=='/'||e.ctrlKey||e.metaKey||e.altKey)return;
      var a=document.activeElement;
      if(a&&a.matches('input,textarea,select,[contenteditable="true"]'))return;
      var home=document.getElementById('tm-home');
      if(home&&!home.classList.contains('tm-hidden'))return;
      var overlay=document.getElementById('tm-ai-overlay');
      if(overlay&&overlay.classList.contains('open'))return;
      var field=document.getElementById('tm-main-search');
      if(field&&field.offsetParent!==null){e.preventDefault();field.focus();}
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
</script>
<!-- TREKMAP_SITEWIDE_UX_END -->'''
if html.count("</body>") != 1:
    raise SystemExit("Cannot safely install sitewide UX: body marker count != 1")
html = html.replace("</body>", block + "\n</body>", 1)
path.write_text(html, encoding="utf-8")
print("TrekMap sitewide UX: preserved original controls and installed responsive/a11y layer")

# Last responsive layer; this site-wide style is intentionally applied before it.
from runpy import run_path
run_path(str(Path(__file__).with_name("apply_desktop_map_layout.py")))
