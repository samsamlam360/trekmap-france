/* Smoke test independent from npm, Android SDK and production. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
const c=JSON.parse(fs.readFileSync('mobile/capacitor.config.json','utf8'));
const p=JSON.parse(fs.readFileSync('mobile/package.json','utf8'));
const w=fs.readFileSync('.github/workflows/android-apk.yml','utf8');
const patch=fs.readFileSync('mobile/scripts/configure-android.mjs','utf8');
const check=fs.readFileSync('mobile/scripts/verify-android.mjs','utf8');
assert.equal(c.appId,'fr.trekmap.france');
assert.equal(p.dependencies['maplibre-gl'],'4.7.1');
assert.equal(c.server.url,'https://trekmap-france.onrender.com');
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
console.log('ANDROID SCAFFOLD PASS: isolated Android workflow, transport, live backend, foreground GPS only, offline warning.');
