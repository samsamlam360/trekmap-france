/* TrekBrain GPX: genuine route geometry, secure XML, offline and no API requests. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync('scripts/apply_trekbrain_map_workspace.py','utf8');
const js=source.match(/<script id="trekbrain-route-workspace-js">([\s\S]*?)<\/script>/)?.[1];
assert.ok(js,'map workspace should include executable script');
new vm.Script(js);
assert.ok(js.includes('data-workspace-action="gpx"'),'both mobile and PC panel should expose GPX');
assert.ok(js.includes("else if(action==='gpx')exportGPX()"),'button must be functional');
assert.ok(js.includes('exportGPX:exportGPX'),'other components can use offline GPX export');
assert.ok(!/fetch\(|XMLHttpRequest/.test(js),'GPX and map workspace must not call remote providers');

const start=js.indexOf('  function validCoords(p){');
const end=js.indexOf('  function updatePanelHeight(){',start);
assert.ok(start>0&&end>start,'real route checks and GPX serializer must be present');
const isolated=js.slice(start,end);
const plan={
  title:'Boucle <Sancy> & "Mont-Dore" éte\\nchemin',
  route_preview:{
    coords:[[45.512345678,2.819999999],[45.52,2.84],[45.53,2.86]]
  }
};
const state={saved:null,clicked:0,removed:0,revoked:0,toasts:[],anchors:[]};
const context=vm.createContext({
  active:true,plan,
  Blob,
  URL:{
    createObjectURL(blob){state.saved=blob;return 'blob:test-trekbrain'},
    revokeObjectURL(url){assert.equal(url,'blob:test-trekbrain');state.revoked++}
  },
  document:{
    body:{appendChild(link){state.anchors.push(link)}},
    createElement(tag){
      assert.equal(tag,'a');
      return {
        setAttribute(){},
        click(){state.clicked++},
        remove(){state.removed++}
      };
    }
  },
  toast(x){state.toasts.push(x)},
  setTimeout(fn){fn();return 1},
});
vm.runInContext(isolated+'\nthis.__gpx={formatGPX,exportGPX};',context);
const generated=context.__gpx.formatGPX(plan);
assert.ok(generated.startsWith('<?xml version="1.0" encoding="UTF-8"?>'));
assert.ok(generated.includes('xmlns="http://www.topografix.com/GPX/1/1"'));
assert.equal((generated.match(/<trkpt /g)||[]).length,3);
assert.ok(generated.includes('lat="45.5123457" lon="2.8200000"'));
assert.ok(generated.includes('lat="45.5300000" lon="2.8600000"'));
assert.ok(generated.includes('&lt;Sancy&gt; &amp; &quot;Mont-Dore&quot;'));
assert.ok(!generated.includes('<Sancy>'),'raw HTML/XML injection must be escaped');
assert.ok(!generated.includes('<ele>'),'never invent elevation points');
assert.equal(context.__gpx.exportGPX(),true);
assert.equal(state.clicked,1);
assert.equal(state.removed,1);
assert.equal(state.revoked,1);
assert.equal(state.saved.type,'application/gpx+xml;charset=utf-8');
assert.ok(state.anchors[0].download.endsWith('.gpx'));
assert.ok(state.anchors[0].download.startsWith('boucle-sancy'));
assert.ok(state.toasts[0].includes('fonds de carte ne sont pas inclus'));
const text=await state.saved.text();
assert.equal(text,generated,'downloaded GPX must match validated pedestrian coordinates');

context.active=false;
assert.equal(context.__gpx.exportGPX(),false,'no export without an active trek');
assert.equal(state.clicked,1);
context.active=true;
const old=context.plan;
for(const bad of [
  {route_preview:{coords:[]}},
  {route_preview:{coords:[[45,5],[95,5]]}},
  {route_preview:{coords:[[45,5],[45,999]]}},
  {route_preview:{coords:[[45,5],["NaN",5]]}},
  {route_preview:{coords:[[45,5],[null,5]]}},
  {route_preview:{coords:[[45,5],[true,5]]}},
  {route_preview:{coords:[[45,5],["",5]]}},
]){
  context.plan=bad;
  assert.equal(context.__gpx.exportGPX(),false,'invalid GPS must not be exported');
}
context.plan=old;
assert.equal(state.clicked,1);
assert.ok(state.toasts.some(x=>x.includes('Aucun tracé GPS')||x.includes('indisponible')));

const workflows=[
  '.github/workflows/trekbrain-scroll-ui.yml',
  '.github/workflows/trekbrain-v9.yml',
  '.github/workflows/render-strict-preflight.yml'
];
for(const file of workflows){
  const text=fs.readFileSync(file,'utf8');
  assert.ok(text.includes('node scripts/test_trekbrain_gpx_export.mjs'),file+' missing GPX regression');
}
console.log('Offline GPX: valid 1.1 XML, full route, injection safe, one download, phone+PC and zero provider calls: PASS');
