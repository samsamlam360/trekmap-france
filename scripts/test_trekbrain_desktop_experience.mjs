/* Desktop TrekBrain layout and keyboard navigation. No network/dependencies. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('scripts/apply_trekbrain_desktop_experience.py','utf8');
const css=source.match(/<style id="trekbrain-desktop-workspace-css">([\s\S]*?)<\/style>/)?.[1];
const script=source.match(/<script id="trekbrain-desktop-workspace-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(css&&script,'desktop CSS and navigation JS must be installed');
new vm.Script(script,{filename:'trekbrain-desktop-workspace.js'});
assert.ok(source.includes('TREKMAP_TREKBRAIN_DESKTOP_2026_START'));
assert.ok(source.includes('TREKMAP_TREKBRAIN_DESKTOP_2026_END'));
assert.ok(source.includes('TREKMAP_MOBILE_MAP_FOCUS_START'));
assert.ok(source.includes('TREKMAP_SCENIC_PHOTOS_START'));
assert.ok(!css.includes('@media(max-width:820px)'),'do not override existing mobile layout');
assert.ok(css.includes('@media screen and (min-width:821px)'),'all desktop rules must be gated');
assert.ok(css.includes('grid-template-columns:clamp(342px,28vw,418px) minmax(0,1fr)'));
assert.ok(css.includes('width:min(1600px,calc(100vw - 56px))'));
assert.ok(css.includes('grid-template-columns:repeat(2,minmax(0,1fr))'));
assert.ok(css.includes('.tm-desk-contents button[aria-current="location"]'));
assert.ok(css.includes('.leaflet-top.leaflet-left .tm-route-day-legend'));
assert.ok(css.includes('.leaflet-bottom.leaflet-right .tm-v91-legend'));
assert.ok(css.includes('max-height:min(42dvh,360px)'),'limit map-legend overlap');
assert.ok(css.includes('focus-visible'),'keyboard indicators remain visible');
assert.ok(!/fetch\s*\(|XMLHttpRequest|localStorage/.test(script),'no API calls, network or storage');
assert.ok(script.includes('if(!isDesktop())'),'desktop navigation must not exist on phones');
assert.ok(script.includes("item.node.focus({preventScroll:true})"),'keyboard focus follows navigation');
assert.ok(script.includes("aria-label','Aller à une section"),'accessible section index');

const render=fs.readFileSync('render.yaml','utf8');
assert.ok(render.includes('python scripts/apply_trekbrain_scenic_photos.py && python scripts/apply_trekbrain_desktop_experience.py && python scripts/render_preflight.py'),
  'desktop enhancement must execute last in Render UI chain');
const workflowNames=[
  '.github/workflows/render-strict-preflight.yml',
  '.github/workflows/trekbrain-scroll-ui.yml',
  '.github/workflows/trekbrain-v9.yml'
];
for(const file of workflowNames){
  const workflow=fs.readFileSync(file,'utf8');
  assert.ok(workflow.includes('python scripts/apply_trekbrain_desktop_experience.py'),file+' must build desktop UI');
  assert.ok(workflow.includes('node scripts/test_trekbrain_desktop_experience.mjs'),file+' must run desktop regression');
}
const html=fs.readFileSync('frontend/index.html','utf8');
if(html.includes('TREKMAP_TREKBRAIN_DESKTOP_2026_START')){
  for(const marker of ['TREKMAP_TREKBRAIN_DESKTOP_2026_START','id="trekbrain-desktop-workspace-css"','id="trekbrain-desktop-workspace-js"']){
    assert.equal(html.split(marker).length-1,1,'desktop UI block must be idempotent: '+marker);
  }
  for(const id of ['tm-ai-prompt','tm-ai-region','tm-ai-days','tm-ai-km','tm-ai-generate','tm-ai-content','tm-ai-result']){
    assert.equal(html.split('id="'+id+'"').length-1,1,'original planner DOM ID preserved: '+id);
  }
}

// Build a tiny browser-like DOM. Exercise desktop and phone transitions,
// actual button activation and asynchronous TrekBrain section rendering.
class Element {
  constructor(tag){
    this.tagName=tag;this.children=[];this.attributes={};this.listeners={};
    this.className='';this.hidden=false;this.removed=false;this.scrollTop=0;
  }
  setAttribute(k,v){this.attributes[k]=String(v)}
  removeAttribute(k){delete this.attributes[k]}
  addEventListener(name,fn){this.listeners[name]=fn}
  appendChild(node){this.children.push(node);return node}
  replaceChildren(...nodes){this.children=[...nodes]}
  querySelectorAll(sel){return sel==='button'?this.children:[]}
  getBoundingClientRect(){return {top:this.top||100}}
  setAttributeNS(){}
  remove(){this.removed=true;this.children=[]}
  focus(options){this.focused=true;this.focusOptions=options}
  scrollTo(options){this.lastScroll=options}
}
const title=new Element('h2');title.top=124;
const essentials=new Element('section');essentials.top=290;
const stages=new Element('section');stages.top=510;
const scenic=new Element('section');scenic.top=830;
const analysis=new Element('section');analysis.top=1120;
const hiddenDetails=new Element('details');hiddenDetails.open=false;
analysis.querySelector=sel=>sel==='.tm-ux-analysis-details'?hiddenDetails:null;
stages.querySelector=sel=>sel===':scope > .tm-ai-stage'?new Element('article'):null;
const all={' .tm-ai-titlebar':title};
const sectionMap={
  '.tm-ai-titlebar':title,'.tm-ux-essentials':essentials,
  '.tm-ux-scenic':scenic,'#tm-v9-panel':analysis
};
const content={
  querySelector(sel){return sectionMap[sel]||null},
  querySelectorAll(sel){return sel==='.tm-ai-section'?[stages]:[]}
};
const pane=new Element('section');pane.top=100;
pane.insertBefore=function(node,ref){
  assert.equal(ref,content);this.children.push(node);this.inserted=(this.inserted||0)+1;
};
const overlay={
  dataset:{},
  querySelector(sel){return sel==='.tm-ai-result'?pane:null}
};
let observerCallback=null;
let viewport=1440;
const listeners={};
const window={
  get innerWidth(){return viewport},
  set innerWidth(value){viewport=value},
  addEventListener(name,fn){listeners[name]=fn},
  matchMedia(query){return {matches:query.includes('reduce')?false:viewport>820}}
};
const document={
  getElementById(id){return id==='tm-ai-overlay'?overlay:id==='tm-ai-content'?content:null},
  createElement(tag){return new Element(tag)}
};
vm.runInNewContext(script,{window,document,
  MutationObserver:class {constructor(cb){observerCallback=cb}observe(){}}
});
assert.equal(pane.inserted,1,'desktop should receive exactly one navigation bar');
const toc=pane.children[0];
assert.equal(toc.className,'tm-desk-contents');
assert.equal(toc.attributes['aria-label'],'Aller à une section du résultat TrekBrain');
assert.deepEqual(toc.children.map(button=>button.textContent),[
  'Résumé','À vérifier','Étapes','Panoramas','Analyse'
]);
assert.equal(toc.children[0].attributes['aria-current'],'location');
toc.children[2].listeners.click();
assert.ok(pane.lastScroll.top>=320&&pane.lastScroll.top<340,'stage navigation must scroll within result panel');
assert.equal(stages.focused,true,'keyboard focus follows selected section');
toc.children[4].listeners.click();
assert.equal(hiddenDetails.open,true,'optional technical analysis can be opened directly');
observerCallback();
assert.equal(pane.inserted,1,'re-render check must not duplicate the toolbar');
window.innerWidth=375;
listeners.resize();
assert.equal(toc.removed,true,'phone layout must not keep a desktop navigation toolbar');
const originalInsertions=pane.inserted;
observerCallback();
assert.equal(pane.inserted,originalInsertions,'phone re-render must not insert desktop controls');
window.innerWidth=1024;
listeners.resize();
assert.equal(pane.inserted,2,'desktop navigation may return after resizing from mobile');
console.log('Desktop UX: responsive modal, 2-col stages, map-space limits, functional keyboard navigation, mobile isolation: PASS');
