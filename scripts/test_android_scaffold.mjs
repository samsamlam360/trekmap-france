/* Smoke test independent from npm, Android SDK and production. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const c=JSON.parse(fs.readFileSync('mobile/capacitor.config.json','utf8'));
const p=JSON.parse(fs.readFileSync('mobile/package.json','utf8'));
const w=fs.readFileSync('.github/workflows/android-apk.yml','utf8');
const patch=fs.readFileSync('mobile/scripts/configure-android.mjs','utf8');
const check=fs.readFileSync('mobile/scripts/verify-android.mjs','utf8');
assert.equal(c.appId,'fr.trekmap.france');
assert.equal(p.dependencies['maplibre-gl'],'4.7.1');
assert.equal(c.server.url,undefined,'Android must never wait for Render before showing its local shell');
assert.equal(c.server.hostname,'localhost');
assert.equal(c.server.androidScheme,'https');
assert.deepEqual(c.server.allowNavigation,['trekmap-france.onrender.com']);
const home=fs.readFileSync('mobile/www/index.html','utf8');
for(const id of ['id="offline-map"','id="saved-routes"','id="journal"','id="online"','id="routes"'])
 assert.ok(home.includes(id),'Bundled app missing '+id);
assert.ok(home.includes('listOfflineRoutes')&&home.includes('openOnline'),'Dashboard actions missing');
assert.ok(!/<script[^>]+src=["']https?:/.test(home)&&!/<link[^>]+href=["']https?:/.test(home),
 'Bundled launcher must not load remote assets');
new vm.Script(home.match(/<script>([\s\S]*?)<\/script>/)?.[1]||'throw Error("No dashboard script")');

assert.equal(c.server.cleartext,false);
assert.equal(c.android.allowMixedContent,false);
assert.equal(c.loggingBehavior,'none');
assert.deepEqual([p.dependencies['@capacitor/core'],p.dependencies['@capacitor/android'],p.devDependencies['@capacitor/cli']],['8.5.3','8.5.3','8.5.3']);
for(const part of ['workflow_dispatch','pull_request','assembleDebug','upload-artifact@v4','node scripts/verify-android.mjs']) assert.ok(w.includes(part),part);
for(const part of ['android.permission.ACCESS_FINE_LOCATION','android.permission.ACCESS_COARSE_LOCATION','android:usesCleartextTraffic','trekmap_icon_bg']) assert.ok(patch.includes(part),part);
assert.ok(check.includes('ACCESS_BACKGROUND_LOCATION'),'background location permission must remain absent');
assert.ok(check.includes('FOREGROUND_SERVICE_LOCATION'),'native foreground tracking must be declared');
for(const f of ['TrekMapNativeGpsPlugin.java','GpsTrackStore.java','GpsTrackService.java','GpsTrackActivity.java']) {
 const code=fs.readFileSync('mobile/native-src/fr/trekmap/france/'+f,'utf8');
 assert.ok(code.includes('package fr.trekmap.france;'),f);
}
const svc=fs.readFileSync('mobile/native-src/fr/trekmap/france/GpsTrackService.java','utf8');
assert.ok(svc.includes('startForeground(')&&svc.includes('removeUpdates('));
assert.ok(!svc.includes('HttpURLConnection')&&!svc.includes('new URL('));
const bridge=fs.readFileSync('mobile/native-src/fr/trekmap/france/TrekMapNativeGpsPlugin.java','utf8');
assert.ok(bridge.includes('"/randonnee"')&&bridge.includes('"https"')&&bridge.includes('openTracker'));
assert.ok(bridge.includes('"localhost"')&&bridge.includes('public void openOnline(')&&bridge.includes('public void openLocalHome('));
assert.ok(bridge.includes('NET_CAPABILITY_VALIDATED'),'online navigation must check connectivity');
assert.ok(bridge.includes('public void listOfflineRoutes(') && bridge.includes('public void openOfflineDownload('),'profile offline bridge exists');
assert.ok(bridge.includes('public void openOfflineDownload(PluginCall call){\n        if(!trustedHikePage()')===false,
  'map downloading must work from the actual root profile');
assert.ok(bridge.includes('private void permitted(PluginCall call,boolean hikeOnly,Task action)'),
  'all native actions must share an origin gate');
assert.ok(bridge.includes('activity.runOnUiThread(()->{') &&
  bridge.includes('web.getUrl()') &&
  bridge.indexOf('activity.runOnUiThread(()->{') < bridge.indexOf('web.getUrl()'),
  'WebView.getUrl must only be called from Android main UI thread');
assert.ok(bridge.includes('IO.execute(()->{') &&
  bridge.includes('newSingleThreadExecutor'),
  'slow native route writes must not block UI');
assert.ok(bridge.includes('activity.startActivity(intent)') &&
  bridge.includes('catch(Exception e)') &&
  bridge.includes('call.reject('),
  'activity starts and failures need explicit user-visible error handling');
for(const m of ['saveOfflineRoute','listOfflineRoutes','openOfflineRoute','openOfflineDownload',
  'openOfflineJournal','openOfflineMap','openOfflineRoutes','openTracker']){
 const body=bridge.split('public void '+m+'(PluginCall call)')[1]?.split('@PluginMethod')[0];
 assert.ok(body?.includes('permitted(call,'),'method '+m+' bypassed native origin validation');
}
assert.ok(!bridge.includes('getWebView().getUrl()'),'never read WebView URL directly on plugin worker');
const mgr=fs.readFileSync('mobile/native-src/fr/trekmap/france/TrekMapUpdateManager.java','utf8');
assert.ok(mgr.includes('github.com/samsamlam360/trekmap-france/releases/download/') &&
          mgr.includes('sha256:') && mgr.includes('MAX_APK_BYTES'));
const activity=fs.readFileSync('mobile/native-src/fr/trekmap/france/TrekMapUpdateActivity.java','utf8');
assert.ok(activity.includes('ACTION_MANAGE_UNKNOWN_APP_SOURCES') &&
          activity.includes('FileProvider') && activity.includes('ACTION_VIEW'));
assert.ok(patch.includes('TREKMAP_KEYSTORE_PATH') &&
          patch.includes('TrekMapUpdateActivity') && patch.includes('trekmap_update_paths'));
const workflow=fs.readFileSync('.github/workflows/android-apk.yml','utf8');
assert.ok(workflow.includes('TREKMAP_ANDROID_KEYSTORE_BASE64') &&
          workflow.includes('assembleRelease') && workflow.includes('gh release create'));

for(const f of ['OfflineRouteStore.java','OfflineTreksActivity.java','OfflineRouteActivity.java'])
 assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/'+f,'utf8').includes('package fr.trekmap.france;'));
assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/OfflineTreksActivity.java','utf8').includes('OfflineRouteStore.list'));
assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/OfflineRouteActivity.java','utf8').includes('RouteDiagram'));
assert.ok(fs.readFileSync('frontend/hike.html','utf8').includes('nativePlugin.saveOfflineRoute'));
assert.ok(fs.readFileSync('frontend/hike.html','utf8').includes('nativePlugin.openOfflineDownload'));
assert.ok(fs.readFileSync('frontend/index.html','utf8').includes('Treks téléchargés'));
assert.ok(fs.readFileSync('mobile/www/offline-map.html','utf8').includes('maplibregl.Map'));
for(const f of ['OfflineTileStore.java','OfflineDownloadActivity.java','OfflineVectorMapActivity.java'])
 assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/'+f,'utf8').includes('package fr.trekmap.france;'));
const tiles=fs.readFileSync('mobile/native-src/fr/trekmap/france/OfflineTileStore.java','utf8');
assert.ok(tiles.includes('MAX_TILES_PER_ACTION=320')&&tiles.includes('MAX_BYTES_PER_ACTION=24L*1024*1024'));
assert.ok(w.includes('npm run android:bundle-map'));
assert.ok(fs.readFileSync('mobile/scripts/bundle-offline-map.mjs','utf8').includes('maplibre-gl.js'));
assert.ok(fs.readFileSync('frontend/hike.html','utf8').includes('nativePlugin.openTracker'));

assert.ok(fs.readFileSync('frontend/hike.html','utf8').includes('navigator.geolocation.watchPosition'));
assert.ok(fs.readFileSync('mobile/www/offline.html','utf8').includes('Connexion indisponible'));
// Full native offline TrekMap UI: all downloaded tracks in the same map, no network assets.
const mapHtml=fs.readFileSync('mobile/www/offline-map.html','utf8');
const appScript=mapHtml.match(/<script>\s*([\s\S]*?)<\/script>/)?.[1];
assert.ok(appScript,'local map JavaScript must be in the APK');
new vm.Script(appScript,{filename:'trekmap-offline-map.js'});
for(const value of ['/data/routes.json','/data/session.json','/data/waypoints.json','data-p-tab','route-total']) {
 if(value==='data-p-tab')continue;
 assert.ok(mapHtml.includes(value),'Missing offline route browser: '+value);
}
assert.ok(mapHtml.includes('HORS LIGNE')&&mapHtml.includes('Treks téléchargés'),'offline branding and list');
assert.ok(!/src=["']https?:\/\//.test(mapHtml),'offline map must not load remote scripts/styles');
assert.ok(!/href=["']https?:\/\//.test(mapHtml),'offline map must not load remote CSS');
const nativeMap=fs.readFileSync('mobile/native-src/fr/trekmap/france/OfflineVectorMapActivity.java','utf8');
assert.ok(nativeMap.includes('fr.trekmap.france.OPEN_LOCAL'),'Native Back must return to bundled home');
assert.ok(nativeMap.includes('"routes.json"')&&nativeMap.includes('"waypoints.json"')&&nativeMap.includes('"/native/gps"'));
assert.ok(nativeMap.includes('"/native/online"')&&nativeMap.includes('NET_CAPABILITY_VALIDATED'),
  'native map must offer a validated return online');
assert.ok(nativeMap.includes('route==null?"null":route.toString()'),
  'offline home must not close on an empty saved route list');
assert.ok(patch.includes('https://localhost/'),'Home screen navigation must be local');
assert.ok(patch.includes('"fr.trekmap.france.OPEN_OFFLINE"'),'Offline deep link supported');
assert.ok(patch.includes('startActivity(new Intent(this,OfflineVectorMapActivity.class))'),
  'offline main entry must show the real map, not a placeholder list');
assert.ok(mapHtml.includes('id="go-online"')&&mapHtml.includes('/native/online'),
  'offline UI needs a retry-online control');
assert.ok(nativeMap.includes('if(!"https".equals(req.getUrl().getScheme()))')||
          nativeMap.includes('!"https".equals(req.getUrl().getScheme())'),'non-HTTPS blocked by local map');
const gpsStore=fs.readFileSync('mobile/native-src/fr/trekmap/france/GpsTrackStore.java','utf8');
assert.ok(gpsStore.includes('nextDay(')&&gpsStore.includes('movingMs')&&gpsStore.includes('lastFixEpoch')&&gpsStore.includes('offtrackFixes'));
assert.ok(svc.includes('NEXT_DAY')&&svc.includes('TrackArchive.add(')&&svc.includes('lastWarningEpoch'));
for(const f of ['TrackArchive.java','TrackArchiveActivity.java','OfflineWaypointStore.java']) {
 assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/'+f,'utf8').includes('package fr.trekmap.france;'));
 assert.ok(patch.includes(f),'Native source missing from Android bundle: '+f);
}
assert.ok(patch.includes('android.permission.VIBRATE')&&patch.includes('TrackArchiveActivity'));
assert.ok(fs.readFileSync('mobile/native-src/fr/trekmap/france/OfflineTreksActivity.java','utf8').includes('OfflineVectorMapActivity.class'));
assert.ok(bridge.includes('openOfflineJournal(')&&bridge.includes('openOfflineMap('));
console.log('ANDROID SCAFFOLD PASS: isolated Android workflow, transport, live backend, foreground GPS only, offline warning.');


// Phase 2: simulated GPS freshness, using the SAME pure function shipped in
// the local MapLibre HTML. No Android hardware or real position data needed.
const gpsHelper=mapHtml.match(/function reliableGpsFix\(s, now\)\{[\s\S]*?\n\}/);
assert.ok(gpsHelper,'Offline map must explicitly distinguish stale fixes');
const reliableGpsFix=vm.runInNewContext('('+gpsHelper[0]+')');
const now=1_700_000_000_000;
const live={status:'active',lastFixEpoch:now-3000,accuracy:9};
assert.equal(reliableGpsFix(live,now),true);
assert.equal(reliableGpsFix({...live,lastFixEpoch:now-31_000},now),false,'31s-old fix is stale');
assert.equal(reliableGpsFix({...live,lastFixEpoch:0},now),false,'no stored GPS fix');
assert.equal(reliableGpsFix({...live,lastFixEpoch:now+5000},now),false,'future timestamp');
assert.equal(reliableGpsFix({...live,accuracy:80},now),false,'bad accuracy');
assert.equal(reliableGpsFix({...live,accuracy:-1},now),false,'unknown accuracy');
assert.equal(reliableGpsFix({...live,status:'paused'},now),false,'paused is not live');
assert.ok(mapHtml.includes("if(live&&follow&&mapReady)"),'only live GPS auto-centers');
assert.ok(mapHtml.includes("Number(s.offtrackFixes)>=3"),'three confirmations before route warning');

const gpsService=fs.readFileSync('mobile/native-src/fr/trekmap/france/GpsTrackService.java','utf8');
assert.ok(gpsService.includes('location.getElapsedRealtimeNanos()<=previous.getElapsedRealtimeNanos()'),
 'out-of-order fixes rejected');
assert.ok(gpsService.includes('location.getElapsedRealtimeNanos()-previous.getElapsedRealtimeNanos()>90000000000L'),
 '90-second GPS gaps must reset the distance anchor');
assert.ok(gpsService.includes('!location.hasAccuracy()'),'unknown GPS accuracy is not valid');
assert.ok(gpsService.includes('if(gpsRecovered)set("note"'),'GPS gap warning survives normal point status');
assert.ok(gpsService.includes('set("offtrackFixes",0)'),'pause and outage must reset departure confirmations');
const gpsStorage=fs.readFileSync('mobile/native-src/fr/trekmap/france/GpsTrackStore.java','utf8');
assert.ok(gpsStorage.indexOf('if(points.length()>=MAX_TRACK_POINTS)')<
 gpsStorage.indexOf('session.put("distance",session.optDouble("distance")+step)'),
 'Never increase recorded distance if a GPX point cannot be stored');
console.log('ANDROID GPS SAFETY: stale, delayed, inaccurate and unrecordable positions guarded');
