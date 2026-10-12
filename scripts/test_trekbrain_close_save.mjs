/* Offline TrekBrain close/save regression. Tests the real JS path, not fabricated outputs. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const planner = fs.readFileSync('scripts/apply_ai_planner.py','utf8');
const route = fs.readFileSync('scripts/apply_route_day_visuals.py','utf8');
const resources = fs.readFileSync('scripts/apply_trekbrain_v9_map_ui.py','utf8');
const workspace = fs.readFileSync('scripts/apply_trekbrain_map_workspace.py','utf8');
const saverBackend = fs.readFileSync('backend/trekbrain_route_persistence_v9.py','utf8');
const appV5 = fs.readFileSync('backend/app_v5.py','utf8');

function compiled(source, scriptID){
  const regex=new RegExp('<script id="'+scriptID+'">([\\s\\S]*?)<\\/script>');
  const code=source.match(regex)?.[1];
  assert.ok(code,'missing '+scriptID);
  new vm.Script(code,{filename:scriptID+'.js'});
  return code;
}
const code=compiled(planner,'trekmap-ai-js');
const dayJS=compiled(route,'trekmap-route-day-visuals-js');
const resourcesJS=compiled(resources,'trekmap-trekbrain-v91-map-js');
const workspaceJS=compiled(workspace,'trekbrain-route-workspace-js');
assert.ok(code.includes('window.TrekMapClearAIPreview=clearAIPreview'));
assert.ok(dayJS.includes('window.TrekMapClearAIRoute=function()'));
assert.ok(resourcesJS.includes('window.TrekMapClearAIResources=clearGroups'));
for(const clear of ['TrekMapClearAIPreview','TrekMapClearAIRoute','TrekMapClearAIResources']){
  assert.ok(workspaceJS.includes('window.'+clear+'?.()'),clear+' should be cleared on X');
}
assert.ok(dayJS.includes('!window.TrekBrainMapWorkspace.isActive()'),
  'pending colored drawing must not resurrect after closing');
assert.ok(resourcesJS.includes('!window.TrekBrainMapWorkspace.isActive()'),
  'pending POI drawing must not resurrect after closing');
assert.ok(!/waypoints\.length<2|pas assez de waypoints/.test(code),
  'save must no longer require a sparse waypoints array');
assert.ok(!resourcesJS.includes("'/ai-redraw'"),
  'saved route must not invoke legacy redrawing API');
assert.ok(resourcesJS.includes('window.TrekMapGeometryPayloadFromAI?.(current)'));
assert.ok(resourcesJS.includes('/ai-geometry'));
assert.ok(resourcesJS.includes('(?:draw|ai-save)'));
assert.ok(appV5.includes('install_trekbrain_route_persistence(app, legacy_main, robust_db_or_503)'));
assert.ok(saverBackend.includes('is_public,duration_days,duration_minutes'));
assert.ok(saverBackend.includes(':owner,FALSE,'));
assert.ok(saverBackend.includes('ST_GeomFromGeoJSON'));
assert.ok(!/get_route\s*\(|ors_get_route\s*\(|elevation_gain\s*\(/.test(saverBackend),
  'saving should not generate a second pedestrian route or elevation request');

// Execute the real save JS functions in a fake app: the user has ZERO waypoints
// but a detailed 5-point route. The backend must receive all five points.
const blockStart=code.indexOf('  function existingRouteCoords(plan){');
const blockEnd=code.indexOf('  window.TrekMapOpenAI=openAI;',blockStart);
assert.ok(blockStart>=0&&blockEnd>blockStart);
const saveCode=code.slice(blockStart,blockEnd);
const points=[[45.13,5.61],[45.14,5.62],[45.15,5.63],[45.16,5.64],[45.17,5.65]];
const plan={
  title:'Boucle du Vercors',region:'Auvergne-Rhône-Alpes',difficulty:'medium',
  duration_days:3,route_preview:{coords:points,distance_km:16,elevation_gain_m:505},
  stages:[{day:1,title:'Les crêtes',distance_km:16,elevation_gain_m:505}],
  // Deliberately no "waypoints": the previous implementation was broken.
  points_of_interest:[],summary:'Parcours pédestre',
};
const btn={disabled:false,textContent:'Enregistrer dans TrekMap'};
const visited=[],network=[],notices=[];
const fakeWindow={
  TrekMapRecordSavedAI(id){visited.push('registered:'+id)},
  TrekMapRefreshAISaveButton(){visited.push('refresh-button')},
  TrekMapOpenTrek(id){visited.push('open:'+id)}
};
const ctx=vm.createContext({
  window:fakeWindow,
  currentPlan:plan,
  $:id=>id==='tm-ai-save'?btn:null,
  api:()=>'',authHeaders:()=>({'Content-Type':'application/json'}),
  fetch:async(url,options)=>{
    network.push({url,options});
    if(url==='/treks/ai-save'){
      assert.equal(options.method,'POST');
      const body=JSON.parse(options.body);
      assert.deepEqual(body.coords,points,'actual route line should be preserved');
      assert.equal(body.elevation_m,505);
      assert.equal(body.name,'Boucle du Vercors');
      assert.equal(body.duration_days,3);
      return {ok:true,status:201,async json(){return {id:739}}};
    }
    assert.equal(url,'/treks/739/extras');
    return {ok:true,async json(){return {message:'ok'}}};
  },
  async loadTraces(){visited.push('reload')},
  closeAI(){visited.push('close')},
  toast:m=>notices.push(m),
  setTimeout(fn){fn();return 1},
  console
});
vm.runInContext(saveCode+'\nwindow.__save={savePlan,existingRouteCoords,trekbrainSavePayload}',ctx);
assert.deepEqual([...fakeWindow.__save.existingRouteCoords(plan)].map(x=>[...x]),points);
assert.throws(()=>fakeWindow.__save.existingRouteCoords({route_preview:{coords:[[45,5]]}}),/tracé/i);
assert.throws(()=>fakeWindow.__save.existingRouteCoords({route_preview:{coords:[[45,5],[200,5]]}}),/invalides/i);
assert.throws(()=>fakeWindow.__save.existingRouteCoords({route_preview:{coords:[[45,5],[45,5]]}}),/différentes/i);
await fakeWindow.__save.savePlan();
assert.deepEqual(network.map(x=>x.url),['/treks/ai-save','/treks/739/extras']);
assert.ok(visited.includes('registered:739'));
assert.ok(visited.includes('reload'));
assert.ok(visited.includes('close'));
assert.ok(visited.includes('open:739'));
assert.equal(btn.disabled,false);
assert.ok(notices.some(x=>x.includes('enregistré en privé')));

// Double-click: the first network request has not finished; the second click
// must neither create a duplicate nor throw an exception.
let finish;
let inFlight=0;
const duplicateCtx=vm.createContext({
  window:{TrekMapRefreshAISaveButton(){}},
  currentPlan:plan,
  $:()=>btn,
  api:()=>'',authHeaders:()=>({}),
  fetch:async(url)=>{
    inFlight++;
    if(url==='/treks/ai-save')return new Promise(resolve=>{finish=()=>resolve({ok:false,status:503,async json(){return {detail:'Service temporairement indisponible.'}}})});
    throw Error('no extras expected');
  },
  async loadTraces(){},closeAI(){},toast:()=>{},setTimeout(fn){fn()},console
});
vm.runInContext(saveCode+'\nwindow.__save={savePlan}',duplicateCtx);
const pending=duplicateCtx.window.__save.savePlan();
await duplicateCtx.window.__save.savePlan();
assert.equal(inFlight,1,'save button double-click must not duplicate records');
finish();
await pending;
assert.equal(btn.disabled,false,'save button must recover after server error');

// The sole API destination for updating existing saved AI routes is the
// authenticated, in-place geometry update. No duplicate trek on a revisit.
assert.ok(resources.includes("endpoint(\`/treks/\${Number(savedTrekId)}/ai-geometry\`)"));
assert.ok(saverBackend.includes('WHERE id=:id'));
assert.ok(saverBackend.includes('owner_id'));
assert.ok(saverBackend.includes('db.rollback()'));

console.log('TrekBrain: X clears route+POI layers, zero-waypoint save preserves geometry, double-click guarded, in-place update: PASS');
