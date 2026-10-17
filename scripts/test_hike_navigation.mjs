/* Offline hiking mode: algorithm and security regression tests. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html=fs.readFileSync('frontend/hike.html','utf8');
const sw=fs.readFileSync('frontend/navigation-worker.js','utf8');
const api=fs.readFileSync('backend/app_v5.py','utf8');
const installer=fs.readFileSync('scripts/apply_hike_navigation_entry.py','utf8');
const chain=fs.readFileSync('scripts/apply_trekbrain_stage_notes.py','utf8');
const main=fs.readFileSync('frontend/index.html','utf8');
assert.ok(html.includes('<div id="nav-map"'),'new standalone navigation view');
assert.ok(html.includes('Distance réellement parcourue'),'GPS travel distance');
assert.ok(html.includes('restant sur le parcours')||html.includes('Restant sur le parcours'));
assert.ok(html.includes('off-line')||html.includes('hors connexion'));
assert.ok(html.includes('OpenFreeMap')&&html.includes('OpenStreetMap'),'attributions visible');
assert.ok(html.includes('navigator.geolocation.watchPosition'),'real GPS watch');
assert.ok(html.includes('lastProjection=nearest;') && html.includes('lastProjection=null;'),
 'GPS projections must be refreshed for each accurate fix and cleared for stale fixes');
const updateBody=html.split('function update(){')[1]?.split('function gpsPosition(pos){')[0];
assert.ok(updateBody?.includes('const nearest=lastGPS?lastProjection:null;') &&
 !updateBody.includes('projected(lastGPS,coords)'),
 'periodic on-screen update must not rescan the entire GPX');

assert.ok(html.includes('id="gps-hud"') && html.includes('id="gps-map-controls"') &&
  html.includes('id="hud-remaining"') && html.includes('id="hud-walked"') &&
  html.includes('id="hud-time"'),'mobile map must expose real GPS stats');
assert.ok(html.includes('id="hike-options"')&&html.includes('id="gps-hud"') &&
  html.includes('id="quick-tools"'),'Options panel replaces duplicate visible GPS controls');
for(const id of ['quick-start','quick-pause','quick-tools','map-recenter','map-full','map-heading'])
 assert.ok(html.includes('id="'+id+'"') &&
   html.includes("el('"+id+"').addEventListener('click'"),
   'mobile control '+id+' needs a working click handler');
assert.ok(html.includes("if(active)el('pause').click()") &&
          html.includes("else el('start').click()"),
  'main GPS button must use existing tested start/pause actions');
assert.ok(html.includes('className=\'option-group\'') &&
  html.includes("group('Cartes hors ligne'") &&
  html.includes("group('Suivi et GPX'") &&
  html.includes("group('Android et carte'"),'Options must classify advanced features');
assert.ok(html.includes('id=\'one-tap-download\'') &&
  html.includes("(native?el('native-tiles'):el('download-all')).click()"),
  'single offline download must dispatch to proper Android or web storage');
assert.ok(html.includes("headingMode&&Number.isFinite(pos.coords.heading)") &&
          html.includes("pos.coords.speed>=0.5"),'map heading only when moving and bearing is valid');
assert.ok(html.includes('aria-valuenow')&&html.includes("remaining=nearest?"),
  'on-map progress bar must follow remaining route distance');

assert.ok(html.includes('id="android-diagnostic"')&&html.includes('nativePlugin.listOfflineRoutes()'),
 'visible bridge diagnosis is required to distinguish browser vs native storage');

assert.ok(html.includes('navigator.wakeLock'),'keep display on if allowed');
assert.ok(html.includes('localStorage.setItem(key'),'track saved locally');
assert.ok(html.includes('id="offline-coverage"') &&
 html.includes('function updateOfflineCoverage()') &&
 html.includes("data.complete===true") && html.includes('Couverture web partielle') &&
 html.includes('Couverture totale NON vérifiée'),
 'Offline status must distinguish proven coverage from an incomplete download');
assert.ok(html.includes('complete:false,partial:true') &&
 html.includes('lastDownloadErrors:fail') &&
 html.includes('lastDownloadBytes:bytes'),
 'New download must invalidate stale complete state and preserve batch results');
assert.ok(html.includes('Carte Android : couverture non vérifiée ici.'),
 'Do not misrepresent browser tiles as native Android offline coverage');
assert.ok(html.includes('download-progress') && html.includes('cache.put(path') &&
  html.includes('caches.open(CACHE_TILES)') && html.includes('new Set(chosen.flatMap(s=>s.files))'),
  'all route sections must save tiles into one deduplicated offline cache');
assert.ok(html.includes('save')||html.includes('saved.points.push('));
assert.ok(html.includes("maximumAge:3000")&&html.includes("accuracy>60"),'accuracy gate and fresh high accuracy');
assert.ok(html.includes('Math.max(45,accuracy*1.8)'),'off-route GPS precision guard');
assert.ok(html.includes('download-progress')&&html.includes('GPX'));
assert.ok(html.includes('MAX_TILES')||html.includes('TILE_CAP=480'),'bounded downloads');
assert.ok(!/fetch\s*\([^)]*\/treks\/[^)]*position/.test(html),'no backend location tracking');
assert.ok(sw.includes('event.respondWith')&&sw.includes('caches.open(')&&sw.includes("url.pathname==='/randonnee'") && sw.includes("const cacheKey=page?"),'service worker for offline');
assert.ok(!sw.includes('tile.openstreetmap.org'),'must not prefetch OSM official tiles');
assert.ok(api.includes('@app.get("/randonnee"')&&api.includes('@app.get("/offline-tiles/{z}/{x}/{y}.pbf"'),'API wired');
assert.ok(api.includes('TrekMapFrance-Navigation/1.0'),'identify application to provider');
assert.ok(api.includes('len(visits) >= 900')&&api.includes('len(upstream.content)>350000'),'rate limit and maximum tile size');
assert.ok(chain.includes('apply_hike_navigation_entry.py'),'production installer chained');
assert.ok(main.includes('hike-navigate-detail')&&main.includes('TrekMapHikingNavigation?.open(t)'),'details open nav');

const m=html.match(/<script>\s*\(function\(\)\{([\s\S]*?)\}\)\(\);\s*<\/script>/);
assert.ok(m,'inline script present');
new vm.Script('(function(){'+m[1]+'})();',{filename:'frontend/hike.html'});
const head=m[1].slice(0,m[1].indexOf('let route=null'));
const math=vm.runInNewContext('const RAD=Math.PI/180;const TILE_PATH="/offline-tiles/";'+
 head.slice(head.indexOf('function dist(a,b){'))+
 ';({dist,validCoords,projected,tileXY,tilesForLine})');

const route=[[45,2],[45,2.01]];
assert.ok(Math.abs(math.dist(...route)-786)<20,'one hundredth longitude around 45deg in meters');
assert.equal(math.validCoords([[45,2],[45,2.01]]).length,2);
assert.equal(math.validCoords([[45,2],[true,2.01]]),null);
assert.equal(math.validCoords([[90,2],[90,2.01]]),null);
assert.equal(math.validCoords([[45,2],[NaN,2.01]]),null);
const on=math.projected([45,2.005],route),off=math.projected([45.002,2.005],route);
assert.ok(on.meters<2,'on route projects close to zero');
assert.ok(on.remaining>370&&on.remaining<420,'distance remaining is along the route');
assert.ok(off.meters>210,'out of route is measurable');
assert.ok(math.projected([45,2.01],route).remaining<2);
const syntheticRegions=[
 [49.70,0.20],[48.82,-3.45],[48.11,7.13],[46.72,5.91],[44.67,3.11],
 [44.88,1.12],[44.32,3.53],[45.31,5.81],[42.91,-0.12],[48.19,7.30],
 [46.12,5.52],[43.46,4.40],[43.86,5.28],[45.13,2.65],[49.88,4.72],
 [46.33,-0.58],[45.68,2.06],[45.37,4.54],[44.31,3.41],[47.36,-2.25]
];
assert.equal(syntheticRegions.length,20);
for(const [idx,[lat,lon]] of syntheticRegions.entries()){
 const path=[[lat,lon],[lat,lon+0.025],[lat+0.015,lon+0.025]];
 const first=math.projected([lat,lon],path);
 const middle=math.projected([lat,lon+0.0125],path);
 const end=math.projected(path[2],path);
 const away=math.projected([lat+0.005,lon+0.0125],path);
 assert.ok(first.meters<1 && first.remaining>middle.remaining &&
  middle.remaining>end.remaining && end.remaining<2,
  'GPS synthetic region '+idx+': monotonic along-track remaining distance');
 assert.ok(away.meters>200,'GPS synthetic region '+idx+': deviation detected');
}
console.log('GPS SIMULATION: 20 geometry cases passed (not a hardware test)');

// Regression: a large route must split instead of refusing >480 map tiles.
assert.ok(html.includes('id="plan-sections"') && html.includes('id="download-all"') &&
          html.includes('id="section-picker"'),'chunked controls visible on mobile');
assert.ok(html.includes('splitAtDistance(') && html.includes('plannedForZoom()'),
  'route can be partitioned into bounded map-tile sections');
assert.ok(html.includes('new Set(plan.flatMap(s=>s.files))'),
  'assembled map reuses a single unique cache of all sections');
const longCoords=Array.from({length:80},(_,i)=>[45+i*0.001,2+i*0.0007]);
const sectionCode=html.slice(html.indexOf('function splitAtDistance('),
                             html.indexOf('async function ensureOfflineShell('));
const segment=vm.runInNewContext('const dist='+math.dist.toString()+';const RAD=Math.PI/180;'+
  sectionCode+';({splitAtDistance,segmentLength})');
const parts=segment.splitAtDistance(longCoords,3000);
assert.ok(parts.length>=3,'long trail must be split into manageable sections');
for(let i=1;i<parts.length;i++)
  assert.deepEqual([...parts[i][0]],[...parts[i-1].at(-1)],'adjacent sections must join at identical points');
const originalMeters=longCoords.slice(1).reduce((n,p,i)=>n+math.dist(longCoords[i],p),0);
const piecesMeters=parts.reduce((n,p)=>n+segment.segmentLength(p),0);
assert.ok(Math.abs(originalMeters-piecesMeters)<2,'splitting must preserve original full trek geometry');
const tiles=math.tilesForLine(route,14);
assert.ok(tiles.length>10&&tiles.length<480,tiles.length+' tiles for a short trek');
assert.ok(tiles.every(p=>/^\/offline-tiles\/(?:9|10|11|12|13|14)\/\d+\/\d+\.pbf$/.test(p)),'tiles served only through controlled source');
assert.equal(new Set(tiles).size,tiles.length,'no duplicate tiles');
// Regression: a previously downloaded page must NOT indefinitely shadow a
// newer site version while online. Offline still uses that refreshed copy.
const handlers={};
const cacheStorage=new Map();
const cacheName='tm-hike-app-v1';
cacheStorage.set(cacheName,new Map([['https://trekmap-france.onrender.com/randonnee',
    new Response('<html>Zone trop vaste (769 tuiles) · ANCIENNE</html>',{status:200})]]));
const fakeCaches={
  async open(name){
    if(!cacheStorage.has(name))cacheStorage.set(name,new Map());
    const store=cacheStorage.get(name);
    const str=req=>typeof req==='string'?req:req.url;
    return {
      async match(key){const x=store.get(str(key));return x?x.clone():undefined},
      async put(key,value){store.set(str(key),value.clone())}
    };
  },
  async keys(){return [...cacheStorage.keys()]},
  async delete(name){return cacheStorage.delete(name)}
};
let networkCalls=0,connected=true;
const ctx={
  URL,Request,Response,caches:fakeCaches,
  self:{
    location:{href:'https://trekmap-france.onrender.com/navigation-worker.js'},
    skipWaiting(){},
    clients:{claim:async()=>{}},
    addEventListener(name,cb){handlers[name]=cb}
  },
  fetch:async ()=>{
    networkCalls++;
    if(!connected)throw new Error('flight mode');
    return new Response('<html>Découper mon trek en sections · ACTUELLE</html>',{status:200});
  }
};
vm.runInNewContext(sw,ctx,{filename:'frontend/navigation-worker.js'});
async function workerGet(url){
 const req=new Request(url);
 let promise;
 handlers.fetch({request:req,respondWith(p){promise=p}});
 assert.ok(promise,'the worker must handle /randonnee');
 const response=await promise;
 return response.text();
}
const current=await workerGet('https://trekmap-france.onrender.com/randonnee');
assert.ok(current.includes('ACTUELLE')&&!current.includes('ANCIENNE'),'online must update a stale offline page');
assert.equal(networkCalls,1,'online first fetches live page');
connected=false;
const offline=await workerGet('https://trekmap-france.onrender.com/randonnee');
assert.ok(offline.includes('ACTUELLE'),'offline must use latest successful HTML');
assert.ok(installer.includes('/randonnee?fresh='),'old installed SW cache must be bypassed by new navigation');
assert.ok(api.includes('no-cache, no-store, must-revalidate'),'HTML must not be cached by HTTP intermediaries');
assert.ok(html.indexOf('nativePlugin?.openOfflineDownload')<html.indexOf("if(!('caches' in window)"),
  'native Android preparation must run before web cache API guards');
// When navigation opens, do not eagerly prepare hundreds of tile groups or
// marshal thousands of coordinates across the native Android bridge.
const finalSetup=html.slice(html.indexOf('setInterval(update,10000);'));
assert.ok(finalSetup.includes('Parcours chargé ('),'route loads without eager tile preparation');
assert.ok(!finalSetup.includes('try{setSections()}catch(e)'),'tile planning must be lazy');
const beforeFunctions=html.slice(html.indexOf('const nativePlugin='),html.indexOf('function nativeCoords()'));
assert.ok(!beforeFunctions.includes('nativePlugin.saveOfflineRoute('),'no native storage writes on page opening');
assert.ok(html.includes('function displayPoints(points,limit=5500)'),'large map preview must be bounded');
assert.ok(html.includes('data:coordinatesGeo(displayPoints(coords))'),'large polyline preview uses a bounded source');
assert.ok(html.includes('function showMapFallback()'),'fallback must be created only when needed');
assert.ok(!html.includes('Math.min(...lon)')&&!html.includes('Math.max(...lat)'),'large coordinate spread can overflow mobile JS stack');
console.log('HIKING CORE PASS: route validation, real traveled-distance geometry, off-route, remaining, offline tiles, limits and privacy');
