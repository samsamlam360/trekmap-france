/* TrekBrain route workspace: no real planning calls or route-provider quota. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('scripts/apply_trekbrain_map_workspace.py','utf8');
const css=source.match(/<style id="trekbrain-route-workspace-css">([\s\S]*?)<\/style>/)?.[1];
const script=source.match(/<script id="trekbrain-route-workspace-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(css&&script,'workspace CSS/JS must be installed');
new vm.Script(script,{filename:'trekbrain-route-workspace.js'});
assert.ok(css.includes('body.tm-brain-route-mode #sidebar'),'filters hidden only in TrekBrain mode');
assert.ok(css.includes('body.tm-brain-route-mode #tm-unified-drawer'),'popular treks hidden in TrekBrain mode');
assert.ok(css.includes('body.tm-brain-route-mode .tm-route-day-legend'),'duplicate route legend hidden');
assert.ok(css.includes('@media(max-width:820px)'),'phone has a real adapted route sheet');
assert.ok(css.includes('env(safe-area-inset-bottom,0px)'),'respect mobile system navigation');
assert.ok(css.includes('.tm-brain-content {\n  min-height:0;flex:1 1 auto;overflow-y:auto;'),
  'long preparation needs and stages scroll inside the available panel space');
assert.ok(!css.includes('position:sticky'), 'footer must not overlap buttons in the scrollable content');
assert.ok(css.includes('.tm-brain-actions'),'save and modify remain accessible');
assert.ok(css.includes('.tm-brain-alert'),'safety warnings are visibly surfaced');
assert.ok(css.includes('.tm-brain-detail'),'stages use the shared scrollable content');
assert.ok(css.includes('focus-visible'),'keyboard focus remains obvious');
assert.ok(css.includes('color:#fff!important;background:#174f38!important'), 'hiking mode action must have high contrast');
assert.ok(script.includes("data-workspace-action=\"fit\""),'recenter action');
assert.ok(script.includes("data-workspace-action=\"save\""),'save action');
assert.ok(script.includes("data-workspace-action=\"exit\""),'return to explorer');
assert.ok(script.includes("data-workspace-action=\"expand\""),'mobile expandable stages');
assert.ok(script.includes('window.TrekBrainMapWorkspace={'));
assert.ok(script.includes('isActive:function(){return active;}'),'map workspace must expose active state');
assert.ok(!/fetch\s*\(|XMLHttpRequest|localStorage|\/ai\/plan/.test(script),'no duplicate route planning nor extra network');
assert.ok(script.includes('if(!p||typeof p!=='), 'invalid/missing planning response must not open');
assert.ok(script.includes('if(!active||!plan||!validCoords(plan))return;'),'recenter only verified coordinates');

const planner=fs.readFileSync('scripts/apply_ai_planner.py','utf8');
assert.ok(planner.includes('window.TrekBrainMapWorkspace?.open(p)'),'only explicit map-preview action opens this mode');
const render=fs.readFileSync('render.yaml','utf8');
assert.ok(render.includes('python scripts/apply_trekbrain_desktop_experience.py && python scripts/apply_trekbrain_map_workspace.py && python scripts/render_preflight.py'),
  'Render builds the map workspace last');
for(const file of [
  '.github/workflows/render-strict-preflight.yml',
  '.github/workflows/trekbrain-scroll-ui.yml',
  '.github/workflows/trekbrain-v9.yml',
]){
  const workflow=fs.readFileSync(file,'utf8');
  assert.ok(workflow.includes('python scripts/apply_trekbrain_map_workspace.py'),file+' must include the new UI');
  assert.ok(workflow.includes('node scripts/test_trekbrain_map_workspace.mjs'),file+' must run route-workspace tests');
}
const html=fs.readFileSync('frontend/index.html','utf8');
if(html.includes('TREKMAP_BRAIN_ROUTE_WORKSPACE_START')){
  for(const marker of ['TREKMAP_BRAIN_ROUTE_WORKSPACE_START','id="trekbrain-route-workspace-js"','id="trekbrain-route-workspace-css"']){
    assert.equal(html.split(marker).length-1,1,'idempotent insertion: '+marker);
  }
  for(const id of ['tm-ai-content','tm-ai-preview','tm-ai-save','sidebar']){
    assert.equal(html.split('id="'+id+'"').length-1,1,'original controls preserved: '+id);
  }
  assert.ok(html.includes("overlay.id='tm-ai-overlay'"),'the existing modal is still initialized');
  assert.ok(html.includes("drawer.id='tm-unified-drawer'"),'the original popular-treks drawer still exists for Explorer');

}

// Run a browser-like integration scenario covering both desktop and mobile.
function classList(){
  const set=new Set();
  return {
    add(...args){args.forEach(s=>set.add(s))},
    remove(...args){args.forEach(s=>set.delete(s))},
    contains(v){return set.has(v)},
    toggle(v,on){
      if(on===undefined)on=!set.has(v);
      if(on)set.add(v);else set.delete(v);
      return on;
    }
  };
}
class FakeElement{
  constructor(tag){
    this.tagName=tag;this.id='';this.attrs={};this.dataset={};
    this.classList=classList();this.listeners={};this.innerHTML='';
    this.hidden=false;this.disabled=false;this.rect={width:365,height:240,left:14};
  }
  setAttribute(k,v){this.attrs[k]=String(v)}
  getAttribute(k){return this.attrs[k]}
  addEventListener(k,fn){this.listeners[k]=fn}
  appendChild(node){this.child=node}
  querySelector(selector){
    if(selector==='[data-workspace-action="expand"]')return this.expandButton;
    return null;
  }
  getBoundingClientRect(){return this.rect}
}
const body=new FakeElement('body');
const styles={};
body.style={
  setProperty(k,v){styles[k]=v},
  removeProperty(k){delete styles[k]},
};
const search=new FakeElement('input');
const originalSave=new FakeElement('button');originalSave.clicked=0;originalSave.click=()=>originalSave.clicked++;
const windowEvents={};
let aiOpened=0,savedOpened=0;
let previewCleared=0,coloredCleared=0,resourcesCleared=0;
const windowObj={
  innerWidth:1440,innerHeight:900,
  addEventListener(k,fn){windowEvents[k]=fn},
  matchMedia(){return {matches:false}},
  TrekMapOpenAI(){aiOpened++},
  TrekMapOpenTrek(){savedOpened++},
  TrekMapClearAIPreview(){previewCleared++},
  TrekMapClearAIRoute(){coloredCleared++},
  TrekMapClearAIResources(){resourcesCleared++},
};
const documentEvents={};
const aiMobileButton=new FakeElement('button');aiMobileButton.dataset.mobileAction='ai';
aiMobileButton.classList.add('active');
const exploreMobileButton=new FakeElement('button');exploreMobileButton.dataset.mobileAction='explore';
const doc={
  body,
  createElement(tag){return new FakeElement(tag)},
  querySelectorAll(selector){
    return selector==='#tm-mobile-nav [data-mobile-action]'?[aiMobileButton,exploreMobileButton]:[];
  },
  getElementById(id){
    return id==='tm-main-search'?search:id==='tm-ai-save'?originalSave:null;
  },
  addEventListener(k,fn){documentEvents[k]=fn},
};
const mapEvents={};
let fitted=0,topPadding=0,bottomPadding=0;
const mapObj={
  on(k,fn){mapEvents[k]=fn},
  invalidateSize(){},
  fitBounds(bounds,opts){
    fitted++;
    topPadding=opts.paddingTopLeft[0];
    bottomPadding=opts.paddingBottomRight[1];
  },
  panInside(){},
};
const leaflet={latLngBounds(){return {isValid(){return true},pad(){return this}}}};
vm.runInNewContext(script,{
  document:doc,window:windowObj,map:mapObj,L:leaflet,
  ResizeObserver:class{observe(){}},
  setTimeout(fn){fn();return 1},
  clearTimeout(){},
  console,
});
const workspace=windowObj.TrekBrainMapWorkspace;
assert.ok(workspace,'browser API exists');
assert.equal(workspace.isActive(),false);
const panel=body.child;
assert.equal(panel.id,'tm-brain-route-panel');
assert.equal(panel.hidden,true,'starts without replacing filter pane');
const invalid={route_preview:{coords:[[91,0],[92,0]]}};
assert.equal(workspace.open(invalid),false,'invalid geometry must never hide explorer');
assert.equal(body.classList.contains('tm-brain-route-mode'),false);
const plan={
  title:'Trois jours dans le Vercors',
  region:'Auvergne-Rhône-Alpes',
  duration_days:3,
  start:{name:'Grenoble'},end:{name:'Lans-en-Vercors'},
  route_preview:{distance_km:61.8,coords:[[45.1,5.7],[45.2,5.8]]},
  stages:[
    {day:1,distance_km:20.6,elevation_gain_m:480,from_name:'Grenoble',to_name:'Saint-Nizier',water_notes:'À vérifier'},
    {day:2,distance_km:20.6,elevation_gain_m:390,from_name:'Saint-Nizier',to_name:'Villard'},
    {day:3,distance_km:20.6,elevation_gain_m:250,from_name:'Villard',to_name:'Lans'}
  ],
  map_resources:{coverage:{water:'partial',days_without_water:[2],food:'partial',days_without_food:[3]}},
  logistics:{nights_missing:1,nights_transfer_required:0}
};
assert.equal(workspace.open(plan),true);
assert.equal(workspace.isActive(),true);
assert.equal(panel.hidden,false);
assert.equal(body.classList.contains('tm-brain-route-mode'),true);
assert.ok(panel.innerHTML.includes('Trois jours dans le Vercors'));
assert.ok(panel.innerHTML.includes('61.8 km'));
assert.ok(panel.innerHTML.includes('20.6 km'));
assert.ok(panel.innerHTML.includes('Eau non vérifiée pour les jours 2'));
assert.ok(panel.innerHTML.includes('Ravitaillement non vérifié pour les jours 3'));
assert.ok(panel.innerHTML.includes('1 nuitée(s) restent sans hébergement identifié'));
assert.ok(panel.innerHTML.includes('Jour 1'));
assert.ok(panel.innerHTML.includes('Jour 3'));
assert.ok(panel.innerHTML.includes('<div class="tm-brain-content">'), 'route needs, overview and tools belong to the scrollable body');
assert.ok(panel.innerHTML.includes('</div></div><div class="tm-brain-actions">'), 'footer follows the closed details and scrollable body');
assert.ok(fitted>=1,'new view should fit the real route');
assert.ok(topPadding>350,'desktop recenter clears the sidebar');
assert.equal(typeof mapEvents.movestart,'function');
assert.equal(typeof mapEvents.popupopen,'function');
const clickAction=action=>{
  panel.listeners.click({target:{closest(){return {dataset:{workspaceAction:action},setAttribute(){}}}}});
};
clickAction('resources');
assert.equal(body.classList.contains('tm-brain-show-resources'),true);
clickAction('resources');
assert.equal(body.classList.contains('tm-brain-show-resources'),false);
clickAction('modify');
assert.equal(aiOpened,1,'existing editor must remain available');
clickAction('save');
assert.equal(originalSave.clicked,1,'existing save control must be reused');
clickAction('exit');
assert.equal(workspace.isActive(),false);
assert.equal(previewCleared,1,'closing the panel removes the old dashed preview');
assert.equal(coloredCleared,1,'closing the panel removes the colored J1/J2 lines');
assert.equal(resourcesCleared,1,'closing the panel removes its resource markers');
assert.equal(body.classList.contains('tm-brain-route-mode'),false);
assert.equal(panel.hidden,true);
clickAction('exit');
assert.equal(previewCleared,1,'closing twice must be idempotent');
assert.equal(aiMobileButton.classList.contains('active'),false,'TrekBrain active tab must be reset');
assert.equal(exploreMobileButton.classList.contains('active'),true,'Explorer tab should be active after exiting');
assert.equal('bottom' in styles,false);

windowObj.innerWidth=375;windowObj.innerHeight=812;
panel.rect={width:357,height:260,left:9};
assert.equal(workspace.open(plan),true);
assert.equal(panel.classList.contains('expanded'),false,'mobile is initially compact');
assert.ok(bottomPadding>=300,'phone recenter clears bottom sheet + navigation');
clickAction('expand');
assert.equal(panel.classList.contains('expanded'),true,'phone expands steps on request');
mapEvents.movestart();
assert.equal(panel.classList.contains('expanded'),false,'moving the map folds mobile steps');
doc.body.classList.add('tm-mobile-filters-open');
workspace.exit();
assert.equal(previewCleared,2);
assert.equal(coloredCleared,2);
assert.equal(resourcesCleared,2);
assert.equal(body.classList.contains('tm-brain-route-mode'),false);
assert.equal(body.classList.contains('tm-brain-show-resources'),false);
assert.equal(panel.hidden,true);
assert.ok(!('bottom' in styles));
assert.ok(!Object.keys(styles).length,'old layout properties must be restored');
assert.equal(workspace.open(plan),true);
windowObj.TrekMapOpenTrek(71);
assert.equal(savedOpened,1);
assert.equal(previewCleared,3,'opening a saved trek clears only the generated preview');
assert.equal(coloredCleared,3);
assert.equal(resourcesCleared,3);
assert.equal(body.classList.contains('tm-brain-route-mode'),false,'opening a saved trek must restore Explorer');

console.log('TrekBrain responsive map workspace: PC/mobile, security alerts, editor/save, recenter, explorer restore PASS');

// All CI pipelines exercising the TrekBrain map also guard the complete site.
await import('./test_sitewide_ux.mjs');
await import('./test_desktop_map_layout.mjs');

// Reuse the existing mandatory UI checks for the optional personal hub.
await import('./test_profile_v2.mjs');
