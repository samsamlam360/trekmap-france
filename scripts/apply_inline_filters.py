"""Final Explorer layout: compact horizontal filters and an on-demand advanced panel.

Installed after the profile/desktop layers by Render and CI. The original filter
elements stay in place: quick controls mirror and dispatch to the original inputs.
No database, API, trek routing or TrekBrain changes.
"""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_INLINE_FILTERS_2026_START -->.*?<!-- TREKMAP_INLINE_FILTERS_2026_END -->\s*",
    "\n", html, flags=re.S,
)
for marker in ("TREKMAP_UNIFIED_EXPERIENCE_START", "TREKMAP_MOBILE_EXPERIENCE_START",
               "TREKMAP_DESKTOP_MAP_2026_START", "TREKMAP_PROFILE_V2_START"):
    if marker not in html:
        raise SystemExit("Inline Explorer filters prerequisite missing: " + marker)

block = r'''<!-- TREKMAP_INLINE_FILTERS_2026_START -->
<style id="trekmap-inline-filters-css">
/* The map is the workspace. No permanently reserved sidebar on desktop. */
#tm-inline-filters{display:none}
@media(min-width:821px){
  #tm-inline-filters{
    position:absolute;z-index:6900;
    top:calc(var(--tm-top) + 9px);
    left:clamp(218px,18vw,304px);right:14px;
    display:flex;align-items:center;gap:7px;
    width:max-content;max-width:calc(100vw - clamp(218px,18vw,304px) - 26px);
    min-height:44px;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;
    pointer-events:none;
  }
  #tm-inline-filters::-webkit-scrollbar{display:none}
  #tm-inline-filters :is(select,button){pointer-events:auto;flex-shrink:0;
    height:42px;min-height:42px;border:1px solid #d5e5dc;border-radius:12px;
    background:rgba(255,255,255,.97);color:#24523d;
    padding:0 13px;font:750 12px Inter,system-ui,sans-serif;
    box-shadow:0 5px 19px rgba(9,49,29,.12);
    backdrop-filter:blur(12px);max-width:190px}
  #tm-inline-filters select{appearance:auto;min-width:146px;cursor:pointer;padding-right:9px}
  #tm-inline-filters select[data-active="true"]{background:#e7f6ec;border-color:#6db590;color:#075b3b}
  #tm-inline-filters button:hover,#tm-inline-filters select:hover{
    background:#eff8f2;border-color:#86bca0}
  #tm-inline-filters button[aria-expanded="true"]{background:#ddf2e6;border-color:#66ac87}
  #tm-inline-filters #tm-inline-advanced{
    background:#0d8159;color:#fff;border-color:#13865c;
    font-weight:850;display:flex;align-items:center;gap:7px}
  #tm-inline-advanced .tm-active-count{display:none;align-items:center;justify-content:center;
    min-width:19px;height:19px;padding:0 5px;border-radius:100px;
    background:#fff;color:#087148;font-size:11px}
  #tm-inline-advanced .tm-active-count[data-visible="true"]{display:inline-flex}
  #sidebar{display:none!important;pointer-events:none!important}
  body.tm-inline-filters-open:not(.tm-brain-route-mode) #sidebar{
    display:block!important;position:absolute!important;z-index:6800!important;
    top:calc(var(--tm-top) + 63px)!important;
    left:clamp(18px,18vw,304px)!important;right:auto!important;
    width:min(400px,calc(100vw - 36px))!important;
    min-width:0!important;max-height:calc(100dvh - var(--tm-top) - 76px)!important;
    opacity:1!important;visibility:visible!important;pointer-events:auto!important}
  body.tm-inline-filters-open #sidebar .filters,
  body.tm-inline-filters-open #sidebar .filters:not(.tm-collapsed){
    display:block!important;width:100%!important;min-width:0!important;
    height:auto!important;min-height:0!important;
    max-height:min(555px,calc(100dvh - var(--tm-top) - 80px))!important;
    padding:57px 14px 14px!important;
    overflow-y:auto!important;border-radius:19px!important;
    border:1px solid #d7e8dd!important;background:rgba(255,255,255,.99)!important;
    box-shadow:0 20px 55px rgba(5,42,24,.24)!important}
  body.tm-inline-filters-open #sidebar .filters.tm-collapsed>*{display:revert!important}
  body.tm-inline-filters-open #sidebar .filters.tm-collapsed>.filter-row{display:grid!important}
  body.tm-inline-filters-open #sidebar .filters.tm-collapsed>#tm-criteria-filters{display:grid!important}
  body.tm-inline-filters-open #sidebar .filters.tm-collapsed>.filter-actions{display:flex!important}
  #tm-unified-drawer,body.tm-filters-collapsed #tm-unified-drawer{
    left:16px!important;right:16px!important}
  .leaflet-left{left:16px!important}
  .leaflet-top{top:67px!important}
  .map-tools{top:68px!important}
  body.tm-brain-route-mode #tm-inline-filters{display:none!important}
  body.tm-brain-route-mode #sidebar{display:none!important}
}
@media(min-width:821px) and (max-width:1239px){
  #tm-inline-filters{left:14px;max-width:calc(100vw - 28px)}
  #tm-inline-filters .tm-inline-extra{display:none}
  body.tm-inline-filters-open #sidebar{left:14px!important}
  .leaflet-top{top:67px!important}
}
@media(max-width:820px){
  #tm-inline-filters{display:none!important}
  /* Keep the established mobile bottom-sheet and its existing close behavior. */
}
</style>
<script id="trekmap-inline-filters-js">
(function(){
  "use strict";
  if(document.getElementById('tm-inline-filters'))return;
  var $=function(id){return document.getElementById(id)};
  var app=$('app'),top=$('tm-unified-topbar'),sidebar=$('sidebar');
  var region=$('region-filter'),difficulty=$('difficulty-filter');
  if(!app||!top||!sidebar||!region||!difficulty)return;
  var strip=document.createElement('nav');
  strip.id='tm-inline-filters';
  strip.setAttribute('aria-label','Filtres rapides des randonnées');
  strip.innerHTML='<select id="tm-inline-region" aria-label="Filtrer par région"></select>'+
    '<select id="tm-inline-difficulty" aria-label="Filtrer par difficulté"></select>'+
    '<button class="tm-inline-extra" type="button" data-filter-target="distance-range">↔ Distance</button>'+
    '<button class="tm-inline-extra" type="button" data-filter-target="elevation-range">△ Dénivelé</button>'+
    '<button class="tm-inline-extra" type="button" data-filter-target="duration-filter">◷ Durée</button>'+
    '<button id="tm-inline-advanced" type="button" aria-controls="sidebar" aria-expanded="false">'+
    '☷ Filtres <span class="tm-active-count" aria-label="Filtres actifs"></span></button>';
  app.appendChild(strip);
  var toggle=$('tm-inline-advanced');
  var panel=sidebar.querySelector('.filters');
  var oldClose=$('tm-filter-toggle');
  var keys=['region-filter','difficulty-filter','distance-range','distance-tolerance',
    'elevation-range','elevation-tolerance','duration-filter','sort-filter',
    'tm-route-filter','tm-season-filter','tm-rating-filter','tm-photo-filter','tm-place-filter'];
  function desktop(){return window.innerWidth>820}
  function closePanel(){
    document.body.classList.remove('tm-inline-filters-open');
    toggle.setAttribute('aria-expanded','false');
  }
  function openPanel(id){
    if(!desktop())return;
    if(document.body.classList.contains('tm-brain-route-mode'))return;
    panel.classList.remove('tm-collapsed');
    document.body.classList.add('tm-inline-filters-open');
    toggle.setAttribute('aria-expanded','true');
    if(oldClose)oldClose.textContent='Fermer';
    if(id)setTimeout(function(){
      var input=$(id);
      if(input){input.scrollIntoView({block:'nearest',behavior:'auto'});
        try{input.focus({preventScroll:true})}catch(_){input.focus()}}
    },0);
  }
  toggle.addEventListener('click',function(){
    if(document.body.classList.contains('tm-inline-filters-open'))closePanel();
    else openPanel();
  });
  strip.querySelectorAll('[data-filter-target]').forEach(function(button){
    button.addEventListener('click',function(){openPanel(button.dataset.filterTarget)});
  });
  if(oldClose)oldClose.addEventListener('click',function(event){
    if(!desktop())return;
    event.preventDefault();event.stopImmediatePropagation();closePanel();
  },true);
  document.addEventListener('pointerdown',function(event){
    if(!desktop()||!document.body.classList.contains('tm-inline-filters-open'))return;
    if(sidebar.contains(event.target)||strip.contains(event.target))return;
    closePanel();
  },true);
  document.addEventListener('keydown',function(event){
    if(event.key==='Escape'&&document.body.classList.contains('tm-inline-filters-open')){
      closePanel();toggle.focus();
    }
  });
  window.addEventListener('resize',function(){if(!desktop())closePanel()});
  new MutationObserver(function(){
    if(document.body.classList.contains('tm-brain-route-mode'))closePanel();
  }).observe(document.body,{attributes:true,attributeFilter:['class']});
  function mirror(source,dest){
    var signature=Array.from(source.options).map(function(o){
      return o.value+'|'+o.textContent+'|'+String(o.disabled);
    }).join('\u0001');
    if(dest.dataset.signature!==signature){
      dest.replaceChildren.apply(dest,Array.from(source.options).map(function(o){return o.cloneNode(true)}));
      dest.dataset.signature=signature;
    }
    if(dest.value!==source.value)dest.value=source.value;
    dest.dataset.active=source.value?'true':'false';
  }
  function sync(){
    mirror(region,$('tm-inline-region'));
    mirror(difficulty,$('tm-inline-difficulty'));
    var active=0;
    ['region-filter','difficulty-filter','distance-range','elevation-range','duration-filter',
      'tm-route-filter','tm-season-filter','tm-rating-filter','tm-photo-filter',
      'tm-place-filter'].forEach(function(id){
      var el=$(id);
      if(el&&String(el.value||'').trim()&&String(el.value)!=='0')active++;
    });
    var label=toggle.querySelector('.tm-active-count');
    label.textContent=String(active);
    label.dataset.visible=active?'true':'false';
    toggle.setAttribute('aria-label',active?'Filtres avancés, '+active+' actifs':'Filtres avancés');
  }
  [['tm-inline-region',region],['tm-inline-difficulty',difficulty]].forEach(function(entry){
    $(entry[0]).addEventListener('change',function(event){
      entry[1].value=event.target.value;
      entry[1].dispatchEvent(new Event('change',{bubbles:true}));
      sync();
    });
  });
  keys.forEach(function(id){
    var el=$(id);
    if(el){el.addEventListener('input',sync);el.addEventListener('change',sync)}
  });
  new MutationObserver(sync).observe(region,{childList:true,subtree:true});
  $('reset-filters')?.addEventListener('click',function(){setTimeout(sync,0)});
  sync();
})();
</script>
<!-- TREKMAP_INLINE_FILTERS_2026_END -->'''

if html.count("</body>") != 1:
    raise SystemExit("Unexpected body closing marker")
html = html.replace("</body>", block + "\n</body>", 1)
path.write_text(html, encoding="utf-8")
print("Explorer horizontal filters installed after all desktop/mobile/profile layers")
