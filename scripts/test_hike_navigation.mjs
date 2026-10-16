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
assert.ok(html.includes('navigator.wakeLock'),'keep display on if allowed');
assert.ok(html.includes('localStorage.setItem(key'),'track saved locally');
assert.ok(html.includes('download-progress')&&html.includes('tiles.put(path'),'tile cache download');
assert.ok(html.includes('save')||html.includes('saved.points.push('));
assert.ok(html.includes("maximumAge:3000")&&html.includes("accuracy>60"),'accuracy gate and fresh high accuracy');
assert.ok(html.includes('Math.max(45,accuracy*1.8)'),'off-route GPS precision guard');
assert.ok(html.includes('download-progress')&&html.includes('GPX'));
assert.ok(html.includes('MAX_TILES')||html.includes('TILE_CAP=480'),'bounded downloads');
assert.ok(!/fetch\s*\([^)]*\/treks\/[^)]*position/.test(html),'no backend location tracking');
assert.ok(sw.includes('event.respondWith')&&sw.includes('caches.open(')&&sw.includes("u.pathname==='/randonnee'"),'service worker for offline');
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
const tiles=math.tilesForLine(route,14);
assert.ok(tiles.length>10&&tiles.length<480,tiles.length+' tiles for a short trek');
assert.ok(tiles.every(p=>/^\/offline-tiles\/(?:9|10|11|12|13|14)\/\d+\/\d+\.pbf$/.test(p)),'tiles served only through controlled source');
assert.equal(new Set(tiles).size,tiles.length,'no duplicate tiles');
console.log('HIKING CORE PASS: route validation, real traveled-distance geometry, off-route, remaining, offline tiles, limits and privacy');
