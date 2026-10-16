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
#tm-journey-days{margin-top:16px;border:1px solid #d6e6db;border-radius:15px;padding:13px;background:#fff}
#tm-journey-days h3{font-size:16px;margin:0 0 4px;color:#174b33}
#tm-journey-days p{margin:0 0 12px;font-size:12px;color:#52695b}
#tm-journey-days details{border:1px solid #dce7df;border-radius:12px;margin:8px 0;overflow:hidden}
#tm-journey-days summary{cursor:pointer;background:#f0f7f2;padding:12px;min-height:45px;font-weight:800;color:#1b5c3d}
#tm-journey-days .tm-j-day-fields{padding:12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
#tm-journey-days .tm-j-day-fields label{display:grid;gap:5px;min-width:0;font-size:12px;font-weight:750;color:#285b40}
#tm-journey-days .tm-j-day-fields input,#tm-journey-days .tm-j-day-fields textarea{min-width:0;width:100%;box-sizing:border-box;border:1px solid #bdcfbf;border-radius:9px;padding:9px;font:inherit;font-size:14px;background:white;color:#123c29}
#tm-journey-days .tm-j-day-fields textarea{min-height:65px;resize:vertical}
#tm-journey-days .tm-j-day-fields label.tm-j-wide{grid-column:span 2}
#tm-journey-days :is(input,textarea):focus-visible{outline:3px solid #e6a933;outline-offset:2px}
@media(max-width:560px){#tm-journey-days .tm-j-day-fields{grid-template-columns:1fr}
#tm-journey-days .tm-j-day-fields label.tm-j-wide{grid-column:span 1}}

#modal .planner #checklist .check-row{display:flex!important;align-items:center!important;gap:10px!important;width:100%!important;min-width:0!important;max-width:100%!important;box-sizing:border-box!important}
#modal .planner #checklist .check-row>input[type=checkbox]{width:20px!important;min-width:20px!important;max-width:20px!important;height:20px!important;min-height:20px!important;max-height:20px!important;flex:0 0 20px!important;padding:0!important;margin:0!important}
#modal .planner #checklist .check-row>input[type=text]{flex:1 1 0%!important;width:0!important;min-width:0!important;max-width:100%!important;min-height:46px!important;box-sizing:border-box!important;font-size:16px!important}
#modal .planner #checklist .check-row>button{flex:0 0 42px!important;width:42px!important;min-width:42px!important;height:44px!important;padding:0!important}
#modal .planner,#modal .planner .form-field,#modal .planner #checklist,#modal .planner #tm-journey-days,#modal .planner #tm-journey-plan-tools{min-width:0!important;max-width:100%!important;box-sizing:border-box!important}
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
   var label=done+' / '+lines.length+' éléments cochés';
   if(out.firstChild.textContent!==label)out.firstChild.textContent=label;
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

 var dayKeys=[
  ['start','Départ / heure','Ex. gare, 8 h'],
  ['end','Arrivée / heure','Ex. village, 17 h'],
  ['distance_km','Distance prévue (km)','Ex. 16'],
  ['water','Points d’eau et fiabilité','Ex. vérifier la fontaine et sa potabilité'],
  ['food','Ravitaillement','Ex. épicerie ouverte ?'],
  ['sleep','Nuitée prévue','Ex. camping, réservation à confirmer'],
  ['transport','Transport','Ex. train retour'],
  ['notes','Notes, météo et sécurité','Observations pour cette journée']
 ];
 function openFor(t,data){
   var root=document.getElementById('checklist')?.closest('.planner');
   if(!root)return;
   document.getElementById('tm-journey-days')?.remove();
   var count=Math.min(60,Math.max(1,Math.ceil(Number(t?.duration_days)||1)));
   var section=document.createElement('section');section.id='tm-journey-days';
   var title=document.createElement('h3');title.textContent='Préparation jour par jour';
   var info=document.createElement('p');
   info.textContent='Prépare chaque journée. Les distances et ressources sont saisies par toi : elles ne sont pas vérifiées automatiquement. Tous les champs sont enregistrés avec la checklist.';
   section.append(title,info);
   var existing=new Map((Array.isArray(data?.days)?data.days:[]).filter(function(d){
     return Number.isInteger(d.day)&&d.day>=1&&d.day<=60;
   }).map(function(d){return [d.day,d]}));
   for(var day=1;day<=count;day++){
     var detail=document.createElement('details');
     detail.dataset.day=String(day);
     detail.open=day===1;
     var summary=document.createElement('summary');summary.textContent='Jour '+day;detail.appendChild(summary);
     var fields=document.createElement('div');fields.className='tm-j-day-fields';
     var values=existing.get(day)||{};
     dayKeys.forEach(function(entry){
       var label=document.createElement('label'),field=entry[0]==='notes'?document.createElement('textarea'):document.createElement('input');
       label.textContent=entry[1];field.dataset.dayField=entry[0];
       field.placeholder=entry[2];field.value=String(values[entry[0]]||'').slice(0,500);
       field.maxLength=500;
       if(entry[0]==='notes')label.className='tm-j-wide';
       else field.type='text';
       label.appendChild(field);fields.appendChild(label);
     });
     detail.appendChild(fields);section.appendChild(detail);
   }
   if(Number(t?.duration_days)>60){
     var note=document.createElement('p');note.textContent='Seules les 60 premières journées peuvent être préparées dans cet éditeur.';section.appendChild(note);
   }
   root.appendChild(section);
 }
 function getDays(){
   return [...document.querySelectorAll('#tm-journey-days details[data-day]')].map(function(detail){
     var result={day:Number(detail.dataset.day)};
     detail.querySelectorAll('[data-day-field]').forEach(function(input){
       result[input.dataset.dayField]=String(input.value||'').trim().slice(0,500);
     });
     return result;
   });
 }
 var modal=document.getElementById('modal');
 if(modal){
   // Only a top-level modal replacement reinitializes the form. Never observe
   // the checklist subtree: editing/counting would otherwise recurse forever.
   // The real trek fiche invokes refresh() after constructing the checklist.
   // A MutationObserver on the modal used to append controls *during* opening
   // and could steal focus or scroll position on mobile. Never observe editing.
   modal.addEventListener('change',progress);
   modal.addEventListener('input',progress);
   modal.addEventListener('click',function(){setTimeout(progress,0)});
   enhance();
 }
 window.TrekMapJourneyPlanner={refresh:function(){enhance();progress()},openFor:openFor,getDays:getDays,templates:templates.map(function(t){return t.label})};
})();
</script>
<!-- TM_JOURNEY_PHASE2_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected body marker")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Phase 2 : assistant de checklist additive, sans migration")

from runpy import run_path
run_path(str(Path(__file__).with_name('apply_journey_phase3.py')))
