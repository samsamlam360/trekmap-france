"""Finish the hiker discovery and trek fact sheet without extra services."""
from pathlib import Path
import re
p=Path(__file__).resolve().parents[1]/"frontend"/"index.html"
html=p.read_text(encoding="utf-8")
html=re.sub(r"\s*<!-- TM_HIKER_DISCOVERY_START -->.*?<!-- TM_HIKER_DISCOVERY_END -->\s*","\n",html,flags=re.S)
if "TM_JOURNEY_PHASE3_START" not in html:
    raise SystemExit("Hiker discovery requires prior user-journey layers")
block=r'''<!-- TM_HIKER_DISCOVERY_START -->
<style id="tm-hiker-discovery-css">
#tm-daily-pace-wrap{display:flex;flex-direction:column;gap:6px;margin:8px 0 14px}
#tm-daily-pace-wrap label{font-size:12px;font-weight:800;color:#28573c}
#tm-daily-pace-filter{width:100%;min-height:44px;padding:9px;border-radius:10px;border:1px solid #b7ccbb;
  font-size:14px;color:#194d33;background:#fff}
#tm-quick-pace-popover[hidden]{display:none!important}
#tm-quick-pace-popover{position:fixed;z-index:11800;width:min(315px,calc(100vw - 16px));padding:15px;
  border:1px solid #c9e1d3;border-radius:16px;background:#fff;color:#183d2a;
  box-shadow:0 15px 48px rgba(5,45,24,.25);box-sizing:border-box}
#tm-quick-pace-popover .tm-quick-pace-head{display:flex;justify-content:space-between;align-items:center;gap:12px}
#tm-quick-pace-popover label{font-size:14px;font-weight:800;color:#24543b}
#tm-quick-pace-popover select{display:block;width:100%;min-height:48px;margin-top:11px;padding:9px;
  border:1px solid #a4c5af;border-radius:10px;font-size:16px;background:#fff;color:#16432b}
#tm-quick-pace-close{min-width:44px;min-height:44px;border:1px solid #c5dccb;border-radius:10px;
  background:#eff7f2;color:#20523b;cursor:pointer}
#tm-quick-pace-popover p{font-size:12px;color:#557363;line-height:1.5;margin:9px 0 0}
#tm-hiker-detail{border:1px solid #d2e2d8;border-radius:14px;padding:13px;margin:14px 0;background:#f5faf6;color:#1b4734}
#tm-hiker-detail h3{font-size:17px;margin:0 0 7px}
#tm-hiker-detail p{margin:5px 0;font-size:13px;line-height:1.5}
#tm-hiker-detail .tm-hiker-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}
#tm-hiker-detail .tm-hiker-metrics>div{padding:11px;border-radius:10px;background:#fff;border:1px solid #dbe9df}
#tm-hiker-detail .tm-hiker-metrics b{display:block;font-size:17px}
#tm-hiker-detail .tm-hiker-metrics small{display:block;color:#576c5f}
#tm-hiker-detail svg{width:100%;height:140px;background:#e9f4ed;border:1px solid #d0dfd6;border-radius:12px}
#tm-hiker-detail .tm-hiker-route-note{font-size:11px;color:#56725f;margin-top:5px}
#tm-hiker-detail .tm-hiker-coords{display:grid;gap:4px;overflow-wrap:anywhere;font-size:12px}
@media(max-width:560px){#tm-hiker-detail svg{height:115px}#tm-hiker-detail .tm-hiker-metrics{grid-template-columns:1fr 1fr}}
</style>
<script id="tm-hiker-discovery-js">
(function(){
 "use strict";
 if(window.TrekMapHikerDetails)return;
 function paceValue(t){
   var days=Number(t?.duration_days),km=Number(t?.distance);
   if(!Number.isFinite(days)||days<1||!Number.isFinite(km)||km<=0)return null;
   return km/days;
 }
 function paceMatches(t){
   var el=document.getElementById('tm-daily-pace-filter');
   if(!el||!el.value)return true;
   var p=paceValue(t);
   if(p===null)return false;
   switch(el.value){
     case '0-10':return p<=10;
     case '10-15':return p>10&&p<=15;
     case '15-20':return p>15&&p<=20;
     case '20-25':return p>20&&p<=25;
     case '25+':return p>25;
   }
   return true;
 }
 var host=document.querySelector('#sidebar .filters');
 if(host){
   var wrap=document.createElement('div');wrap.id='tm-daily-pace-wrap';
   var label=document.createElement('label');label.htmlFor='tm-daily-pace-filter';label.textContent='Moyenne indicative par jour';
   var select=document.createElement('select');select.id='tm-daily-pace-filter';
   [['','Toutes les distances par jour'],['0-10','Jusqu’à 10 km/jour'],
    ['10-15','Plus de 10 à 15 km/jour'],['15-20','Plus de 15 à 20 km/jour'],
    ['20-25','Plus de 20 à 25 km/jour'],['25+','Plus de 25 km/jour']
   ].forEach(function(opt){var o=document.createElement('option');o.value=opt[0];o.textContent=opt[1];select.appendChild(o)});
   wrap.append(label,select);
   host.appendChild(wrap);
   select.addEventListener('change',function(){
     // Preserve the single authoritative map/list filtering pipeline.
     document.getElementById('duration-filter')?.dispatchEvent(new Event('change',{bubbles:true}));
   });
   document.getElementById('reset-filters')?.addEventListener('click',function(){
     select.value='';
     document.getElementById('duration-filter')?.dispatchEvent(new Event('change',{bubbles:true}));
   });
   var quick=document.getElementById('tm-inline-advanced');
   if(quick&&!document.getElementById('tm-inline-pace')){
     var b=document.createElement('button');b.id='tm-inline-pace';b.type='button';b.textContent='⌁ Km / jour';
     b.title='Filtrer par moyenne de kilomètres par jour';
     var pop=document.createElement('div');
     pop.id='tm-quick-pace-popover';
     pop.hidden=true;pop.setAttribute('role','dialog');pop.setAttribute('aria-labelledby','tm-quick-pace-heading');
     var head=document.createElement('div');head.className='tm-quick-pace-head';
     var caption=document.createElement('label');caption.id='tm-quick-pace-heading';
     caption.htmlFor='tm-quick-pace-select';caption.textContent='Distance moyenne par jour';
     var dismiss=document.createElement('button');dismiss.type='button';dismiss.id='tm-quick-pace-close';
     dismiss.textContent='×';dismiss.setAttribute('aria-label','Fermer le filtre Km par jour');
     head.append(caption,dismiss);
     var quickSelect=document.createElement('select');quickSelect.id='tm-quick-pace-select';
     [...select.options].forEach(function(option){quickSelect.appendChild(option.cloneNode(true))});
     var note=document.createElement('p');note.textContent='Ce filtre s’applique immédiatement à la carte et aux treks affichés.';
     pop.append(head,quickSelect,note);document.body.appendChild(pop);
     b.setAttribute('aria-haspopup','dialog');
     b.setAttribute('aria-controls','tm-quick-pace-popover');
     b.setAttribute('aria-expanded','false');
     function close(){
       if(pop.hidden)return;
       pop.hidden=true;b.setAttribute('aria-expanded','false');
     }
     function position(){
       var rect=b.getBoundingClientRect(),w=pop.getBoundingClientRect().width||315;
       pop.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-w-8))+'px';
       var height=pop.getBoundingClientRect().height||190;
       pop.style.top=Math.max(8,Math.min(rect.bottom+8,window.innerHeight-height-8))+'px';
     }
     b.addEventListener('click',function(){
       if(!pop.hidden){close();return}
       quickSelect.value=select.value;
       pop.hidden=false;b.setAttribute('aria-expanded','true');position();
       quickSelect.focus({preventScroll:true});
     });
     dismiss.addEventListener('click',function(){close();b.focus({preventScroll:true})});
     quickSelect.addEventListener('change',function(){
       select.value=quickSelect.value;
       select.dispatchEvent(new Event('change',{bubbles:true}));
       close();b.focus({preventScroll:true});
     });
     select.addEventListener('change',function(){quickSelect.value=select.value});
     document.addEventListener('pointerdown',function(e){
       if(!pop.hidden&&!pop.contains(e.target)&&!b.contains(e.target))close();
     },true);
     document.addEventListener('keydown',function(e){
       if(!pop.hidden&&e.key==='Escape'){e.preventDefault();close();b.focus({preventScroll:true})}
     });
     window.addEventListener('resize',function(){if(!pop.hidden)position()});
     window.TrekMapDailyPaceQuick={open:function(){b.click()},close:close,select:quickSelect};
     quick.parentNode.insertBefore(b,quick);
   }
 }
 function safeCoords(t){
   if(!Array.isArray(t?.coords)||t.coords.length<2)return [];
   return t.coords.filter(function(p){
     return Array.isArray(p)&&p.length>=2&&p.slice(0,2).every(function(n){return n!==null&&n!==''&&Number.isFinite(Number(n))})&&
       Math.abs(Number(p[0]))<=90&&Math.abs(Number(p[1]))<=180;
   }).map(function(p){return [Number(p[0]),Number(p[1])]});
 }
 function svgRoute(points){
   if(points.length<2)return null;
   var step=Math.max(1,Math.ceil(points.length/1000)),a=points.filter(function(_,i){return i%step===0});
   if(a[a.length-1]!==points[points.length-1])a.push(points[points.length-1]);
   var mean=(a.reduce(function(n,p){return n+p[0]},0)/a.length)*Math.PI/180;
   var cos=Math.max(.1,Math.cos(mean));
   var xs=a.map(function(p){return p[1]*cos}),ys=a.map(function(p){return p[0]});
   var x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
   var w=Math.max(1e-6,x1-x0),h=Math.max(1e-6,y1-y0),scale=Math.min(350/w,96/h);
   var left=25+(350-w*scale)/2,top=17+(96-h*scale)/2;
   var xy=function(i){return [(left+(xs[i]-x0)*scale).toFixed(1),(top+(y1-ys[i])*scale).toFixed(1)]};
   var poly=a.map(function(_,i){return xy(i).join(',')}).join(' ');
   var start=xy(0),end=xy(a.length-1);
   return '<svg viewBox="0 0 400 130" role="img" aria-label="Tracé réel du trek, schéma sans fond topographique">'+
     '<polyline fill="none" stroke="#147b54" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="'+poly+'"/>'+
     '<circle cx="'+start[0]+'" cy="'+start[1]+'" r="6" fill="#2186c4" stroke="white" stroke-width="2"/>'+
     '<circle cx="'+end[0]+'" cy="'+end[1]+'" r="6" fill="#d35d31" stroke="white" stroke-width="2"/></svg>';
 }
 function augment(t){
   var modal=document.getElementById('modal'),grid=modal?.querySelector('.detail-grid');
   if(!modal||!grid||!t||document.getElementById('tm-hiker-detail'))return;
   var details=document.createElement('section');details.id='tm-hiker-detail';
   var head=document.createElement('h3');head.textContent='Informations pour préparer ce trek';details.appendChild(head);
   var avg=paceValue(t),duration=Number(t.duration_days||0);
   var metrics=document.createElement('div');metrics.className='tm-hiker-metrics';
   var values=[
     [avg!==null?avg.toFixed(1)+' km/jour':'Non renseignée','Distance moyenne indicative'],
     [duration>=1?Math.ceil(duration)+' journée(s)':'Non renseignées','Journées de préparation']
   ];
   values.forEach(function(v){
     var tile=document.createElement('div'),b=document.createElement('b'),small=document.createElement('small');
     b.textContent=v[0];small.textContent=v[1];tile.append(b,small);metrics.appendChild(tile);
   });
   details.appendChild(metrics);
   var points=safeCoords(t),image=svgRoute(points);
   if(image){
     var visual=document.createElement('div');visual.innerHTML=image;details.appendChild(visual);
     var msg=document.createElement('p');msg.className='tm-hiker-route-note';
     msg.textContent='Le dessin représente la géométrie enregistrée, pas un profil altimétrique ni une carte IGN.';details.appendChild(msg);
     var coords=document.createElement('div');coords.className='tm-hiker-coords';
     var format=function(p){return p.map(function(x){return x.toFixed(5)}).join(', ')};
     var dep=document.createElement('span'),end=document.createElement('span');
     dep.textContent='Départ : '+format(points[0]);
     end.textContent='Arrivée : '+format(points[points.length-1]);
     coords.append(dep,end);details.appendChild(coords);
   }else{
     var unavailable=document.createElement('p');unavailable.textContent='Tracé détaillé indisponible. Vérifie le GPX avant toute randonnée.';details.appendChild(unavailable);
   }
   var note=document.createElement('p');note.textContent='Avant de partir : confirmer météo, eau potable, hébergements, éventuelles fermetures et transports. Ces éléments ne sont pas garantis par la fiche.';
   details.appendChild(note);
   grid.insertAdjacentElement('afterend',details);
 }
 window.TrekMapHikerDetails={augment:augment,paceValue:paceValue,paceMatches:paceMatches,svgRoute:svgRoute};
})();
</script>
<!-- TM_HIKER_DISCOVERY_END -->'''
if html.count("</body>")!=1:raise SystemExit("Unexpected closing body marker")
p.write_text(html.replace("</body>",block+"\n</body>",1),encoding="utf-8")
print("Discovery: average daily km filter and route-backed detailed trek facts")

from runpy import run_path
run_path(str(Path(__file__).with_name('apply_trekbrain_stage_notes.py')))
