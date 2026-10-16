"""Phase 1 : filtres actifs indépendamment annulables, sans perturber les contrôles existants."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TM_JOURNEY_PHASE1_START -->.*?<!-- TM_JOURNEY_PHASE1_END -->\s*","\n",html,flags=re.S)
for marker in ("TREKMAP_INLINE_FILTERS_2026_START","TREKMAP_MOBILE_EXPERIENCE_START"):
    if marker not in html: raise SystemExit("Phase 1 prerequisite missing: "+marker)
block=r'''<!-- TM_JOURNEY_PHASE1_START -->
<style id="tm-journey-filters-style">
#tm-journey-active-filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center;min-width:0}
#tm-journey-active-filters:empty{display:none}
#tm-journey-active-filters button{min-height:36px;padding:7px 11px;border:1px solid #b5d8c4;
  background:#eaf7ef;color:#155338;border-radius:999px;font-weight:750;font-size:12px;cursor:pointer}
#tm-journey-active-filters button:hover{background:#d5efdf}
#tm-journey-active-filters button:focus-visible{outline:3px solid #e4a900;outline-offset:2px}
@media(min-width:821px){
 body > #tm-journey-active-filters:not(:empty){position:fixed;z-index:6750;top:calc(var(--tm-top) + 62px);
  left:clamp(218px,18vw,304px);max-width:calc(100vw - clamp(218px,18vw,304px) - 26px);
  max-height:86px;overflow-y:auto;pointer-events:auto}
 @media(max-width:1239px){body > #tm-journey-active-filters:not(:empty){left:14px;max-width:calc(100vw - 28px)}}
}
@media(max-width:820px){
 #tm-journey-active-filters{padding:6px 0}
 #tm-journey-active-filters button{min-height:44px}
}
</style>
<script id="tm-journey-filters-js">
(function(){
 "use strict";
 if(window.TrekMapJourneyFilters)return;
 var ids=['region-filter','difficulty-filter','duration-filter','tm-route-filter','tm-season-filter','tm-rating-filter','tm-photo-filter','tm-place-filter','distance-range','elevation-range','tm-daily-pace-filter'];
 var names={'region-filter':'Région','difficulty-filter':'Difficulté','duration-filter':'Durée','tm-route-filter':'Parcours','tm-season-filter':'Saison','tm-rating-filter':'Avis','tm-photo-filter':'Photos','tm-place-filter':'Lieu','distance-range':'Distance','elevation-range':'Dénivelé','tm-daily-pace-filter':'Km / jour'};
 var group=document.createElement('div');
 group.id='tm-journey-active-filters';
 group.setAttribute('aria-label','Filtres appliqués, retirer un filtre');
 function holder(){
   var desktop=document.getElementById('tm-inline-filters');
   var mobile=document.querySelector('#sidebar .filters');
   var target=window.innerWidth>820?document.body:mobile;
   if(target&&group.parentNode!==target)target.appendChild(group);
 }
 function active(el,id){
   if(!el)return false;
   var v=String(el.value||'').trim();
   if(!v)return false;
   if(id==='distance-range'||id==='elevation-range')return Number(v)>0;
   return true;
 }
 function textFor(el,id){
   if(el.tagName==='SELECT'&&el.selectedOptions&&el.selectedOptions[0]){
     return names[id]+' : '+el.selectedOptions[0].textContent.trim().slice(0,42);
   }
   return names[id]+' : '+String(el.value);
 }
 function clear(el){
   el.value=(el.type==='range'?'0':'');
   el.dispatchEvent(new Event('input',{bubbles:true}));
   el.dispatchEvent(new Event('change',{bubbles:true}));
 }
 function draw(){
   holder();
   group.replaceChildren();
   var filters=ids.filter(function(id){return active(document.getElementById(id),id)});
   var search=document.getElementById('tm-main-search');
   if(search&&search.value.trim())filters.unshift('__search__');
   filters.forEach(function(id){
     var el=id==='__search__'?search:document.getElementById(id);
     var button=document.createElement('button');
     button.type='button';
     var label=id==='__search__'?'Recherche : '+search.value.trim().slice(0,40):textFor(el,id);
     button.textContent=label+' ×';
     button.setAttribute('aria-label','Retirer '+label);
     button.addEventListener('click',function(){
       if(id==='__search__'){
         var reset=document.getElementById('tm-main-search-clear');
         if(reset)reset.click();else{clear(search);var legacy=document.getElementById('search');if(legacy)clear(legacy);}
       }else clear(el);
       draw();
     });
     group.appendChild(button);
   });
 }
 ids.forEach(function(id){
   var el=document.getElementById(id);
   if(el){el.addEventListener('input',draw);el.addEventListener('change',draw)}
 });
 document.getElementById('tm-main-search')?.addEventListener('input',draw);
 document.getElementById('tm-main-search-clear')?.addEventListener('click',function(){setTimeout(draw,0)});
 document.getElementById('reset-filters')?.addEventListener('click',function(){setTimeout(draw,0)});
 window.addEventListener('resize',draw,{passive:true});
 var region=document.getElementById('region-filter');
 if(region)new MutationObserver(draw).observe(region,{childList:true,subtree:true});
 window.TrekMapJourneyFilters={refresh:draw,getActiveCount:function(){return group.children.length}};
 draw();
})();
</script>
<!-- TM_JOURNEY_PHASE1_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected closing body marker")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Phase 1 : filtres annulables et recherche synchronisée")

from runpy import run_path
run_path(str(Path(__file__).with_name('apply_journey_phase2.py')))
