/* Execute the real readiness UI, planner renderer and map workspace offline. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const read=name=>fs.readFileSync(new URL(name,import.meta.url),'utf8');
const script=(source,id)=>source.match(new RegExp('<script id="'+id+'">([\\s\\S]*?)<\\/script>'))?.[1];
const ui=script(read('apply_trekbrain_v9_ui.py'),'trekmap-trekbrain-v9-js');
const planner=script(read('apply_ai_planner.py'),'trekmap-ai-js');
const workspaceScript=script(read('apply_trekbrain_map_workspace.py'),'trekbrain-route-workspace-js');
for(const source of [ui,planner,workspaceScript]){assert.ok(source);new vm.Script(source)}
const extract=(source,start,end)=>{
  const a=source.indexOf(start),b=source.indexOf(end,a);
  assert.ok(a>=0&&b>a,'real formatter must remain available');return source.slice(a,b);
};

function classes(){
  const values=new Set();return {add(...x){x.forEach(v=>values.add(v))},remove(...x){x.forEach(v=>values.delete(v))},contains:x=>values.has(x),toggle(x,on){if(on===undefined)on=!values.has(x);on?values.add(x):values.delete(x);return on}};
}
let observer=()=>{},appends=0;
class Element{
  constructor(tag='div'){this.tagName=tag;this.classList=classes();this.dataset={};this.listeners={};this.children=[];this.attrs={};this.value='';this.checked=true;this.disabled=false;this.hidden=false;this.style={display:'',setProperty(){},removeProperty(){}};this.html='';this.focuses=0}
  setAttribute(k,v){this.attrs[k]=String(v)}
  addEventListener(type,fn){(this.listeners[type]??=[]).push(fn)}
  focus(){this.focuses++}
  scrollTo(){}
  scrollIntoView(){}
  closest(selector){return selector==='details'?this.details||null:null}
  getBoundingClientRect(){return {width:365,height:340,left:14}}
  set innerHTML(value){
    this.html=value;this.children=[];
    this.buttons=[...value.matchAll(/data-readiness-action="(\d+)"/g)].map(match=>{const b=new Element('button');b.dataset.readinessAction=match[1];return b});
  }
  get innerHTML(){return this.html+this.children.map(x=>x.innerHTML).join('')}
  querySelector(selector){
    if(selector==='#tm-v9-panel')return this.children.find(x=>x.id==='tm-v9-panel')||null;
    if(selector==='.tm-v9-readiness')return this.innerHTML.includes('class="tm-v9-readiness"')?this:null;
    return null;
  }
  querySelectorAll(selector){return selector==='[data-readiness-action]'?[...(this.buttons||[]),...this.children.flatMap(x=>x.querySelectorAll(selector))]:[]}
  appendChild(node){this.children.push(node);node.parent=this;appends++;if(this.id==='tm-ai-content')observer()}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this)}
  click(){this.clicks=(this.clicks||0)+1;(this.listeners.click||[]).forEach(fn=>fn({preventDefault(){},stopPropagation(){},target:this}))}
}
const controls=new Map();
const control=id=>{if(!controls.has(id)){const x=new Element();x.id=id;controls.set(id,x)}return controls.get(id)};
const content=control('tm-ai-content'),overlay=control('tm-ai-overlay'),shell=new Element(),side=new Element(),body=new Element('body');
shell.classList.add('has-result');
control('tm-ai-prompt').value='Ma demande originale';control('tm-ai-region').value='Jura';control('tm-ai-days').value='3';control('tm-ai-km').value='18';
const advanced=new Element('details');control('tm-ai-km').details=advanced;
const timers=[];
let responseData,responseOK=true,requests=0,opened=0,clears=0,saves=0;
const window={innerWidth:1440,innerHeight:900,matchMedia:()=>({matches:false}),addEventListener(){},
  fetch:async()=>{requests++;return {ok:responseOK,status:responseOK?200:422,clone:()=>({json:async()=>responseData})}},
  TrekMapOpenAI(){opened++;overlay.classList.add('open');overlay.setAttribute('aria-hidden','false');timers.push({fn:()=>control('tm-ai-prompt').focus(),delay:80})},
  TrekMapClearAIPreview(){clears++},TrekMapClearAIRoute(){clears++},TrekMapClearAIResources(){clears++},
};
control('tm-ai-save').click=()=>{saves++};
const document={body,
  getElementById(id){return id==='tm-ai-launch'?null:control(id)},
  createElement:tag=>new Element(tag),
  querySelector(selector){return selector==='#tm-ai-overlay .tm-ai-shell'?shell:selector==='#tm-ai-overlay .tm-ai-side'?side:null},
  querySelectorAll:()=>[],addEventListener(){},
};
const context=vm.createContext({window,document,console,fetch:(...args)=>window.fetch(...args),AbortController,
  MutationObserver:class{constructor(fn){observer=fn}observe(){}},
  setTimeout(fn,delay=0){timers.push({fn,delay});return timers.length},clearTimeout(){},
  ResizeObserver:class{observe(){}},
});
function flush(){let n=0;while(timers.length){assert.ok(n++<30,'observer must settle');timers.sort((a,b)=>a.delay-b.delay);timers.shift().fn()}}
vm.runInContext(ui,context);
const readiness=window.TrekMapTripReadiness;
assert.ok(readiness,'shared formatter must exist');
const incomplete={title:'Trois jours',duration_days:3,decision_summary:{quality:98,important:[]},trekbrain:{version:'v9'},
  route_preview:{coords:[[46.6,5.8],[46.7,5.9]],distance_km:54,fallback:false},stages:[],
  trip_readiness:{version:1,status:'incomplete',label:'Préparation incomplète',route_validated:true,requirements:{},issues:[
    {code:'water_missing',requirement:'water',days:[3,2,2],detail:'Sources à confirmer'},
    {code:'food_missing',requirement:'food',days:[3],detail:'Commerce absent'},
    {code:'night_missing',requirement:'accommodation',days:[2],detail:'Nuitée non résolue'},
    {code:'distance_exceeded',requirement:'distance',days:[1],detail:'22 km pour une cible de 18 km'},
    {code:'objective_unsatisfied',requirement:'objective',days:[2],detail:'Lac <img src=x onerror=alert(1)> non atteint'},
    {code:'transit_missing',requirement:'transit',days:[1],detail:'Accès en bus à organiser'},
  ],actions:[{type:'edit_request',label:'Ajuster la durée <script>',detail:'Préparer les besoins & vérifier',suggested_changes:{daily_km:16,unknown:'ignored'}}]},
};
const html=readiness.html(incomplete);
assert.ok(html.includes('Préparation incomplète')&&html.includes('Tracé pédestre validé'));
assert.ok(html.includes('Eau · jours 2, 3')&&html.includes('Ravitaillement · jour 3')&&html.includes('Nuitées · jour 2'));
assert.ok(html.includes('Distance · jour 1')&&html.includes('Objectif · jour 2')&&html.includes('Transports · jour 1'),'all issues survive five-group summary');
assert.equal((html.match(/<li>/g)||[]).length,4,'issues share compact groups without dropping mandatory objectives');
assert.ok(html.includes('&lt;img')&&html.includes('&lt;script&gt;')&&html.includes('&amp;'),'all backend text must be escaped');
assert.ok(!html.includes('<img')&&!html.includes('<script>'));
assert.ok(html.includes('type="button"')&&html.includes('role="region"'));

const escLine=planner.split('\n').find(line=>line.includes('const esc='));
const essential=extract(planner,'  function essentialChecks(p){','\n  function isViewpoint');
const renderPlan=extract(planner,'  function renderPlan(p){','\n  function clearAIPreview');
Object.assign(context,{$:id=>control(id),difficultyLabel:{},shell,scenicCards:()=>'',waterLabel:()=>['Eau',''],sourceLink:()=>'',previewPlan(){},closeAI(){},savePlan(){saves++}});
vm.runInContext(escLine+'\n'+essential+'\n'+renderPlan,context);
context.p=incomplete;vm.runInContext('renderPlan(p)',context);
assert.ok(content.innerHTML.indexOf('Préparation incomplète')<content.innerHTML.indexOf('tm-ai-stats'),'status precedes result cards');
const action=content.querySelectorAll('[data-readiness-action]')[0];
readiness.bind(content,incomplete);readiness.bind(content,incomplete);
assert.equal(action.listeners.click.length,1,'binding remains idempotent');
action.click();flush();
assert.equal(opened,1);assert.equal(control('tm-ai-km').value,'16');assert.equal(advanced.open,true);
assert.equal(control('tm-ai-km').focuses,1,'focus reaches the edited field after modal opens');
assert.equal(control('tm-ai-prompt').value,'Ma demande originale');
assert.equal(control('tm-ai-region').value,'Jura');assert.equal(shell.classList.contains('has-result'),false);
assert.equal(overlay.attrs['aria-hidden'],'false');assert.equal(clears,0);assert.equal(requests,0,'edit preserves route and does not recalculate');
readiness.edit(incomplete,{suggested_changes:{days:99,daily_km:'bad',require_water:'false'}});flush();
assert.equal(control('tm-ai-days').value,'3');assert.equal(control('tm-ai-water').checked,true,'invalid suggestions cannot disable a requirement');

// Accepted edits must change the written target as well as form defaults,
// because the backend deliberately gives natural-language constraints priority.
const measured={...incomplete,effective_request:{days:2,daily_km:16}};
control('tm-ai-prompt').value='Une boucle de 2 jours, environ 16 km par jour, avec eau.';
readiness.edit(measured,{suggested_changes:{days:3,daily_km:19.5}});flush();
assert.equal(control('tm-ai-prompt').value,'Une boucle de 3 jours, environ 19.5 km par jour, avec eau.');
control('tm-ai-prompt').value='Une nouvelle demande de 5 jours à 22 km par jour.';
readiness.edit(measured,{suggested_changes:{days:4,daily_km:18}});flush();
assert.equal(control('tm-ai-prompt').value,'Une nouvelle demande de 5 jours à 22 km par jour.','do not overwrite newer written constraints');
control('tm-ai-prompt').value='Une boucle de 2 jours, maximum 16 km par jour.';
readiness.edit(measured,{suggested_changes:{daily_km:19.5}});flush();
assert.ok(control('tm-ai-prompt').value.includes('maximum 16 km'),'a hard limit is never silently relaxed');
assert.equal(requests,0);assert.equal(clears,0);

responseData=incomplete;
await window.fetch('/ai/plan');await Promise.resolve();flush();
assert.equal((content.innerHTML.match(/class="tm-v9-readiness"/g)||[]).length,1,'analysis must not duplicate the existing readiness summary');
assert.ok(content.innerHTML.indexOf('Préparation incomplète')<content.innerHTML.indexOf('Voir l’analyse détaillée'));
assert.ok(content.innerHTML.includes('<b>98</b>'),'score stays in the secondary analysis');
const appendCount=appends;
vm.runInContext(ui,context);observer();flush();
assert.equal(appends,appendCount,'reinstalled script and DOM observer do not redraw');

const ready={...incomplete,trip_readiness:{version:1,status:'ready',route_validated:true,issues:[],actions:[]}};
assert.ok(readiness.html(ready).includes('Besoins confirmés'));
const refused={trip_readiness:{version:1,status:'refused',route_validated:false,issues:[{requirement:'route',days:[],detail:'Routage indisponible'}],actions:[]}};
assert.ok(readiness.html(refused).includes('Tracé refusé'));
const old={...incomplete,trip_readiness:undefined,map_resources:{coverage:{water:'partial',days_without_water:[2],food:'partial',days_without_food:[3]}},
  logistics:{nights_missing:1,nights:[{night:2,status:'unresolved'}]},decision_summary:{quality:99,important:['Objectif obligatoire non satisfait']}};
const oldHTML=readiness.html(old);
assert.ok(oldHTML.includes('À vérifier')&&!oldHTML.includes('Besoins confirmés'));
assert.ok(oldHTML.includes('Objectif obligatoire non satisfait')&&oldHTML.includes('Eau · jour 2')&&oldHTML.includes('Nuitées · jour 2'),'legacy warnings stay visible');

responseOK=false;responseData={detail:refused};content.innerHTML='<div class="tm-ai-warning">Impossible de préparer ce trek.</div>';
await window.fetch('/ai/plan');await Promise.resolve();flush();
assert.ok(content.innerHTML.includes('Tracé refusé'),'structured HTTP failures show their refused verdict');

// The mobile map summary uses the same formatter before its folded stage list.
window.innerWidth=390;
vm.runInContext(workspaceScript,context);
assert.equal(window.TrekBrainMapWorkspace.open(incomplete),true);
const mapPanel=body.children.find(x=>x.id==='tm-brain-route-panel');
assert.ok(mapPanel.innerHTML.indexOf('Préparation incomplète')<mapPanel.innerHTML.indexOf('tm-brain-detail'));
assert.ok(mapPanel.innerHTML.includes('Objectif · jour 2')&&mapPanel.innerHTML.includes('Nuitées · jour 2'));
assert.equal(mapPanel.classList.contains('expanded'),false,'needs remain outside folded mobile details');
mapPanel.listeners.click[0]({target:{closest:()=>({dataset:{workspaceAction:'save'}})}});
assert.equal(saves,1,'existing save action remains available');
const beforeRequests=requests,beforeClears=clears;
mapPanel.listeners.click[0]({target:{closest:()=>({dataset:{workspaceAction:'modify'}})}});flush();
assert.equal(requests,beforeRequests);assert.equal(clears,beforeClears);assert.equal(window.TrekBrainMapWorkspace.isActive(),true,'modifying the form preserves the displayed route');
console.log('Trip readiness UI: faithful verdict, every missing need/day, escaped text, real form focus, no auto recalculation, stable modal/map/save PASS');
