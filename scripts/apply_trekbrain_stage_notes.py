"""Allow in-place annotations per TrekBrain day without pretending to reroute."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TM_STAGE_NOTES_START -->.*?<!-- TM_STAGE_NOTES_END -->\s*","\n",html,flags=re.S)
if "TM_HIKER_DISCOVERY_START" not in html or "TREKMAP_BRAIN_ROUTE_WORKSPACE_START" not in html:
    raise SystemExit("Missing TrekBrain workspace stage annotation prerequisites")
block=r'''<!-- TM_STAGE_NOTES_START -->
<style id="tm-stage-notes-css">
#tm-stage-note-dialog{border:1px solid #bfd8c8;border-radius:18px;padding:22px;max-width:min(530px,calc(100vw - 26px));
  width:100%;box-sizing:border-box;box-shadow:0 20px 68px rgba(9,38,22,.34);color:#173d2e;background:#fff}
#tm-stage-note-dialog::backdrop{background:rgba(8,29,17,.55)}
#tm-stage-note-dialog h2{font-size:19px;margin:0 0 7px}
#tm-stage-note-dialog p{font-size:13px;color:#566e5c;line-height:1.5}
#tm-stage-note-dialog textarea{display:block;width:100%;min-height:125px;resize:vertical;
  box-sizing:border-box;border:1px solid #afcdb7;border-radius:10px;padding:11px;font:14px/1.5 system-ui}
#tm-stage-note-dialog .tm-stage-note-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
#tm-stage-note-dialog button{min-height:44px;border-radius:10px;padding:9px 12px;border:1px solid #b7d3c4;background:#eff7f1;color:#144d32;font-weight:800}
#tm-stage-note-dialog button.tm-save{background:#0e754b;border-color:#0e754b;color:#fff}
#tm-brain-route-panel .tm-stage-user-note{margin-top:10px;padding:9px;border-radius:9px;
  background:#eff8f2;border:1px solid #cde6d6;white-space:pre-wrap;color:#20523a;font-size:12px;line-height:1.5}
#tm-stage-note-dialog :is(textarea,button):focus-visible{outline:3px solid #e1a42a;outline-offset:2px}
</style>
<script id="tm-stage-notes-js">
(function(){
 "use strict";
 if(window.TrekMapStageEdit)return;
 var dialog=document.createElement('dialog');dialog.id='tm-stage-note-dialog';
 dialog.innerHTML='<h2 id="tm-stage-note-title">Notes pour cette journée</h2>'+
   '<p>Tu peux modifier tes notes sans recalculer les autres journées. Les étapes et le tracé GPS restent inchangés.</p>'+
   '<label for="tm-stage-note-text">Mes ajustements personnels</label>'+
   '<textarea id="tm-stage-note-text" maxlength="1000" placeholder="Ex. dormir au gîte, vérifier la fontaine, prévoir une pause..."></textarea>'+
   '<div class="tm-stage-note-actions"><button type="button" class="tm-save" data-stage-action="save">Enregistrer la note</button>'+
   '<button type="button" data-stage-action="replan">Modifier le tracé avec TrekBrain</button>'+
   '<button type="button" data-stage-action="cancel">Annuler</button></div>'+
   '<p>Notes enregistrées dans ce navigateur uniquement. Une modification du tracé demande un nouveau calcul et des vérifications.</p>';
 document.body.appendChild(dialog);
 var currentDay=0;
 function activePlan(){return window.TrekBrainMapWorkspace?.getPlan?.()||null}
 function key(plan){
   if(!plan)return null;
   var coords=plan.route_preview?.coords||[];
   if(!Array.isArray(coords)||coords.length<2)return null;
   var values=String(plan.title||'')+':'+coords.length+':'+JSON.stringify(coords.slice(0,3))+':'+JSON.stringify(coords.slice(-3));
   var hash=2166136261;
   for(var i=0;i<values.length;i++){hash^=values.charCodeAt(i);hash=Math.imul(hash,16777619)}
   return 'tm-stage-annotations-v1-'+(hash>>>0).toString(16);
 }
 function read(plan){
   try{var raw=localStorage.getItem(key(plan));var obj=JSON.parse(raw||'{}');return obj&&typeof obj==='object'&&!Array.isArray(obj)?obj:{}}catch(_){return {}}
 }
 function write(plan,obj){
   try{localStorage.setItem(key(plan),JSON.stringify(obj));return true}
   catch(_){if(typeof toast==='function')toast('Stockage local indisponible. La note n’a pas été enregistrée.');return false}
 }
 function renderNotes(plan,panel){
   if(!panel||!plan)return;
   var notes=read(plan);
   panel.querySelectorAll('.tm-brain-stage').forEach(function(stage,i){
     stage.querySelector('.tm-stage-user-note')?.remove();
     var value=String(notes[String(i+1)]||'').trim();
     if(!value)return;
     var p=document.createElement('p');p.className='tm-stage-user-note';p.textContent='✎ Ma note : '+value;stage.appendChild(p);
   });
 }
 function open(day){
   var plan=activePlan(),num=Number(day),stages=plan?.stages;
   if(!plan||!Array.isArray(stages)||!Number.isInteger(num)||num<1||num>stages.length)return false;
   currentDay=num;
   dialog.querySelector('#tm-stage-note-title').textContent='Adapter mes notes : jour '+num;
   dialog.querySelector('#tm-stage-note-text').value=String(read(plan)[String(num)]||'');
   if(dialog.open)dialog.close();
   dialog.showModal();dialog.querySelector('#tm-stage-note-text').focus();
   return true;
 }
 dialog.addEventListener('click',function(e){
   var action=e.target.closest('button[data-stage-action]')?.dataset.stageAction;
   if(!action)return;
   if(action==='cancel'){dialog.close();return}
   if(action==='save'){
     var plan=activePlan(),note=dialog.querySelector('#tm-stage-note-text').value.trim().slice(0,1000);
     if(!plan)return;
     var state=read(plan);
     if(note)state[String(currentDay)]=note;else delete state[String(currentDay)];
     if(write(plan,state)){
       dialog.close();
       renderNotes(plan,document.getElementById('tm-brain-route-panel'));
       if(typeof toast==='function')toast('Note du jour '+currentDay+' conservée dans ce navigateur.');
     }
   }else if(action==='replan'){
     dialog.close();
     document.querySelector('#tm-brain-route-panel [data-workspace-action="modify"]')?.click();
     var input=document.getElementById('tm-ai-prompt');
     if(input){
       var instruction='Réévaluer le tracé du jour '+currentDay+' et conserver les autres journées lorsque cela est géographiquement possible.';
       if(!input.value.includes(instruction))input.value=(input.value.trim()+'\n'+instruction).trim();
       input.dispatchEvent(new Event('input',{bubbles:true}));
     }
   }
 });
 window.TrekMapStageEdit={open:open,renderNotes:renderNotes,read:read};
})();
</script>
<!-- TM_STAGE_NOTES_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected HTML body")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("TrekBrain personal day notes installed without recalculating GPS geometry")
