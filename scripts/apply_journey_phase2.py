"""Phase 2 : enrichir la préparation des treks enregistrés, sans changer l'API ni Neon."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TM_JOURNEY_PHASE2_START -->.*?<!-- TM_JOURNEY_PHASE2_END -->\s*","\n",html,flags=re.S)
if "TM_JOURNEY_PHASE1_START" not in html or "function openPlan(" not in html:
    raise SystemExit("Phase 2 requires base planner and phase 1")
block=r'''<!-- TM_JOURNEY_PHASE2_START -->
<style id="tm-journey-plan-style">
#tm-journey-plan-tools{border:1px solid #d8e8dc;background:#f5faf6;padding:13px;border-radius:14px;margin-top:15px}
#tm-journey-plan-tools h3{margin:0 0 5px;font-size:15px;color:#155239}
#tm-journey-plan-tools p{margin:4px 0 10px;color:#536b5d;font-size:12px;line-height:1.5}
#tm-journey-plan-tools .tm-j-prepared-presets{display:flex;flex-wrap:wrap;gap:8px}
#tm-journey-plan-tools button{background:white;color:#16563b;border:1px solid #bcd6c4;border-radius:10px;
padding:9px 12px;min-height:42px;font-weight:700;font-size:12px}
#tm-journey-plan-tools button:hover{background:#e9f5ed}
#tm-journey-progress{margin-top:11px;font-weight:750;font-size:13px;color:#20523c}
#tm-journey-progress small{display:block;font-size:11px;font-weight:450;color:#65756b;margin-top:4px}
</style>
<script id="tm-journey-plan-js">
(function(){
 "use strict";
 if(window.TrekMapJourneyPlanner)return;
 var templates=[
   {label:'🎒 Matériel',items:['Sac et chaussures adaptés','Vêtements pluie et froid','Trousse de premiers secours','Carte/GPX et batterie de secours']},
   {label:'💧 Eau & ravitaillement',items:['Vérifier les points d’eau potable pour chaque jour','Prévoir une réserve d’eau suffisante','Vérifier horaires et ouverture des commerces']},
   {label:'⛺ Nuitées',items:['Confirmer les nuits et réservations','Vérifier la légalité du bivouac ou du camping','Prévoir une solution alternative']},
   {label:'🚆 Accès & sécurité',items:['Vérifier trains et bus aller/retour','Partager son itinéraire et son heure de retour','Contrôler la météo et les alertes officielles','Vérifier les éventuelles fermetures de sentiers']}
 ];
 function row(list,text){
   var r=document.createElement('div');r.className='check-row';
   var cb=document.createElement('input');cb.type='checkbox';cb.setAttribute('aria-label','Élément terminé');
   var input=document.createElement('input');input.type='text';input.value=text;input.maxLength=200;input.autocomplete='off';
   var del=document.createElement('button');del.type='button';del.className='danger-btn';del.textContent='×';del.setAttribute('aria-label','Supprimer cet élément');
   del.addEventListener('click',function(){r.remove();progress()});
   r.append(cb,input,del);list.appendChild(r);
 }
 function normalized(s){return String(s||'').trim().normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
 function progress(){
   var list=document.getElementById('checklist'),out=document.getElementById('tm-journey-progress');
   if(!list||!out)return;
   var lines=[...list.querySelectorAll('.check-row')].filter(function(r){return r.querySelector('input[type="text"]')?.value.trim()});
   var done=lines.filter(function(r){return r.querySelector('input[type="checkbox"]')?.checked}).length;
   out.firstChild.textContent=done+' / '+lines.length+' éléments cochés';
 }
 function enhance(){
   var list=document.getElementById('checklist');
   var planner=list&&list.closest('.planner');
   if(!planner||document.getElementById('tm-journey-plan-tools'))return;
   var tools=document.createElement('section');
   tools.id='tm-journey-plan-tools';
   var h=document.createElement('h3');h.textContent='Aide à la préparation';tools.appendChild(h);
   var info=document.createElement('p');info.textContent='Ajoute des vérifications à ta checklist, sans perdre les éléments existants.';tools.appendChild(info);
   var buttons=document.createElement('div');buttons.className='tm-j-prepared-presets';tools.appendChild(buttons);
   templates.forEach(function(t){
     var b=document.createElement('button');b.type='button';b.textContent=t.label;
     b.addEventListener('click',function(){
       var existing=new Set([...list.querySelectorAll('.check-row input[type="text"]')].map(function(i){return normalized(i.value)}));
       var added=0;
       t.items.forEach(function(item){
         if(existing.has(normalized(item)))return;
         if(list.querySelectorAll('.check-row').length>=60)return;
         row(list,item);existing.add(normalized(item));added++;
       });
       progress();
       if(typeof toast==='function')toast(added?added+' vérifications ajoutées. Pense à enregistrer.':'Ces vérifications figurent déjà dans la checklist.');
     });
     buttons.appendChild(b);
   });
   var bar=document.createElement('div');bar.id='tm-journey-progress';
   bar.appendChild(document.createTextNode(''));
   var help=document.createElement('small');help.textContent='Une checklist cochée ne garantit ni la potabilité de l’eau ni l’ouverture des hébergements.';bar.appendChild(help);
   tools.appendChild(bar);planner.appendChild(tools);
   progress();
 }
 var modal=document.getElementById('modal');
 if(modal){
   new MutationObserver(function(){enhance();progress()}).observe(modal,{childList:true,subtree:true});
   modal.addEventListener('change',progress);
   modal.addEventListener('input',progress);
   modal.addEventListener('click',function(){setTimeout(progress,0)});
   enhance();
 }
 window.TrekMapJourneyPlanner={refresh:enhance,templates:templates.map(function(t){return t.label})};
})();
</script>
<!-- TM_JOURNEY_PHASE2_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected body marker")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Phase 2 : assistant de checklist additive, sans migration")
