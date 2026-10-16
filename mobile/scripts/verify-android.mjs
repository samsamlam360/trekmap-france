import assert from 'node:assert/strict';
import fs from 'node:fs';
const conf=JSON.parse(fs.readFileSync('capacitor.config.json','utf8'));
const pkg=JSON.parse(fs.readFileSync('package.json','utf8'));
assert.equal(conf.appId,'fr.trekmap.france');
assert.equal(conf.server.url,'https://trekmap-france.onrender.com');
assert.equal(conf.server.cleartext,false);
assert.equal(conf.android.allowMixedContent,false);
assert.equal(conf.android.webContentsDebuggingEnabled,false);
for(const name of ['@capacitor/core','@capacitor/android']) assert.equal(pkg.dependencies[name],'8.5.3');
assert.equal(pkg.devDependencies['@capacitor/cli'],'8.5.3');
assert.ok(fs.existsSync('www/index.html')&&fs.existsSync('www/offline.html'));
const xml=fs.readFileSync('android/app/src/main/AndroidManifest.xml','utf8');
for(const permission of ['INTERNET','ACCESS_COARSE_LOCATION','ACCESS_FINE_LOCATION'])
 assert.ok(xml.includes('android.permission.'+permission),permission+' not declared');
assert.ok(xml.includes('android:usesCleartextTraffic="false"'),'HTTP must remain disabled');
assert.ok(!xml.includes('android.permission.ACCESS_BACKGROUND_LOCATION'),'do not promise background GPS');
assert.ok(xml.includes('android.permission.FOREGROUND_SERVICE_LOCATION'),'Native location service permission required');
assert.ok(xml.includes('android:foregroundServiceType="location"'),'Foreground location service declaration required');
assert.ok(xml.includes('android.permission.FOREGROUND_SERVICE'),'Foreground service permission required');
assert.ok(xml.includes('android.permission.POST_NOTIFICATIONS'),'Visible tracking notification');
for(const f of ['TrekMapNativeGpsPlugin.java','GpsTrackStore.java','GpsTrackService.java','GpsTrackActivity.java','MainActivity.java'])
 assert.ok(fs.existsSync('android/app/src/main/java/fr/trekmap/france/'+f), f);
assert.ok(fs.existsSync('android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml'));
const appgradle=fs.readFileSync('android/app/build.gradle','utf8');
assert.ok(appgradle.includes('fr.trekmap.france'),'applicationId mismatch');
console.log('ANDROID CONFIG PASS: native GPS recording, explicit foreground service, permissions, protected HTTPS origin, icon.');
