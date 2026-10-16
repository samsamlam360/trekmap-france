// Configure the freshly generated Capacitor 8 Android shell.
// Explicit opt-in foreground location service supports recording while the display is locked.
import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve('android/app/src/main');
const manifest=path.join(root,'AndroidManifest.xml');
if(!fs.existsSync(manifest)) throw Error('Projet natif absent : lance npm run android:add');
let xml=fs.readFileSync(manifest,'utf8');
if(!xml.includes('<manifest') || !xml.includes('<application')) throw Error('AndroidManifest.xml inattendu');
for(const permission of ['android.permission.INTERNET','android.permission.ACCESS_NETWORK_STATE','android.permission.ACCESS_COARSE_LOCATION','android.permission.ACCESS_FINE_LOCATION','android.permission.FOREGROUND_SERVICE','android.permission.FOREGROUND_SERVICE_LOCATION','android.permission.POST_NOTIFICATIONS','android.permission.REQUEST_INSTALL_PACKAGES','android.permission.VIBRATE']){
  if(!xml.includes('android:name="'+permission+'"')){
    xml=xml.replace(/(<application\b)/, '    <uses-permission android:name="'+permission+'" />\n\n    $1');
  }
}
if(!xml.includes('android.hardware.location.gps')){
  xml=xml.replace(/(<application\b)/, '    <uses-feature android:name="android.hardware.location.gps" android:required="false" />\n\n    $1');
}
if(!xml.includes('android:usesCleartextTraffic="false"')){
  xml=xml.replace(/<application\b/, '<application android:usesCleartextTraffic="false"');
}
if(!xml.includes('fr.trekmap.france.GpsTrackService')){
  xml=xml.replace('</application>', `
        <activity android:name="fr.trekmap.france.GpsTrackActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.OfflineTreksActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.OfflineRouteActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.OfflineDownloadActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.OfflineVectorMapActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.TrackArchiveActivity" android:exported="false" />
        <activity android:name="fr.trekmap.france.TrekMapUpdateActivity" android:exported="false" />
        <provider android:name="androidx.core.content.FileProvider"
            android:authorities="fr.trekmap.france.apkprovider"
            android:grantUriPermissions="true" android:exported="false">
            <meta-data android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/trekmap_update_paths"/>
        </provider>
        <service android:name="fr.trekmap.france.GpsTrackService"
            android:exported="false" android:foregroundServiceType="location" />
    </application>`);
}
fs.writeFileSync(manifest,xml);
const javaDest=path.join(root,'java/fr/trekmap/france');
const nativeSrc=path.resolve('native-src/fr/trekmap/france');
fs.mkdirSync(javaDest,{recursive:true});
for(const file of ['TrekMapNativeGpsPlugin.java','GpsTrackStore.java','GpsTrackService.java','GpsTrackActivity.java','TrekMapUpdateManager.java','TrekMapUpdateActivity.java','OfflineRouteStore.java','OfflineTreksActivity.java','OfflineRouteActivity.java','OfflineTileStore.java','OfflineDownloadActivity.java','OfflineVectorMapActivity.java','TrackArchive.java','TrackArchiveActivity.java','OfflineWaypointStore.java']){
  fs.copyFileSync(path.join(nativeSrc,file),path.join(javaDest,file));
}
// Register only an explicit native tracker launcher. No direct GPS data sent to the WebView.
fs.writeFileSync(path.join(javaDest,'MainActivity.java'), `package fr.trekmap.france;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import com.getcapacitor.BridgeActivity;
public class MainActivity extends BridgeActivity {
    private boolean updateCheckStarted = false;
    private boolean offlineScreenVisible = false;
    private boolean hasNetwork(){
        ConnectivityManager cm=(ConnectivityManager)getSystemService(CONNECTIVITY_SERVICE);
        NetworkCapabilities caps=cm==null?null:cm.getNetworkCapabilities(cm.getActiveNetwork());
        return caps!=null &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED);
    }
    private void showNativeOffline(){
        if(offlineScreenVisible)return;
        offlineScreenVisible=true;
        startActivity(new Intent(this,OfflineTreksActivity.class));
    }
    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(TrekMapNativeGpsPlugin.class);
        super.onCreate(savedInstanceState);
    }
    @Override public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if("fr.trekmap.france.RELOAD_ONLINE".equals(intent.getAction()) && hasNetwork()){
            offlineScreenVisible=false;
            if(getBridge()!=null && getBridge().getWebView()!=null)
                getBridge().getWebView().loadUrl("https://trekmap-france.onrender.com/");
        }
    }
    @Override public void onResume() {
        super.onResume();
        if(!hasNetwork()){
            showNativeOffline();
            return;
        }
        offlineScreenVisible=false;
        if(updateCheckStarted) return;
        updateCheckStarted = true;
        long previous = getSharedPreferences("tm_android_updates",MODE_PRIVATE).getLong("checked_at",0);
        long now = System.currentTimeMillis();
        if(now-previous<6*60*60*1000L) return;
        getSharedPreferences("tm_android_updates",MODE_PRIVATE).edit().putLong("checked_at",now).apply();
        new Thread(()->{
            try {
                TrekMapUpdateManager.Release r=TrekMapUpdateManager.latest();
                if(r==null||r.version<=TrekMapUpdateManager.installedVersion(this))return;
                runOnUiThread(()->{
                    if(isFinishing()||isDestroyed())return;
                    new AlertDialog.Builder(this)
                        .setTitle("Mise à jour TrekMap disponible")
                        .setMessage("Une nouvelle version Android est disponible. Tes données sont conservées si l'application est mise à jour sans être désinstallée.")
                        .setNegativeButton("Plus tard",null)
                        .setPositiveButton("Mettre à jour",(d,w)->
                            startActivity(new Intent(this,TrekMapUpdateActivity.class))).show();
                });
            } catch(Exception ignored) {
                // Network might be unavailable when hiking. No intrusive pop-up.
            }
        }).start();
    }
}
`);
const updateXml=path.join(root,'res/xml');
fs.mkdirSync(updateXml,{recursive:true});
fs.writeFileSync(path.join(updateXml,'trekmap_update_paths.xml'),
  '<?xml version="1.0" encoding="utf-8"?>\n<paths xmlns:android="http://schemas.android.com/apk/res/android">'+
  '<cache-path name="signed-update" path="updates/" /></paths>\n');
// Extra WebView asset routing is AndroidX WebKit, maintained by Google.
const gradle=path.resolve('android/app/build.gradle');
let groovy=fs.readFileSync(gradle,'utf8');
if(!groovy.includes('androidx.webkit:webkit:')){
 groovy+='\n'+'dependencies { implementation "androidx.webkit:webkit:1.12.1" }'+'\n';
}
if(!groovy.includes('// TrekMap stable version and signing configuration')) {
 const version=Number(process.env.TREKMAP_VERSION_CODE||1000);
 if(!Number.isSafeInteger(version)||version<2||version>2147483647)throw Error('Invalid APK versionCode');
 groovy+=`
\n// TrekMap stable version and signing configuration.
android.defaultConfig.versionCode = ${version}
android.defaultConfig.versionName = "1.0.${version}"
if(System.getenv('TREKMAP_KEYSTORE_PATH')) {
  android.signingConfigs.create('trekmapRelease') {
    storeFile file(System.getenv('TREKMAP_KEYSTORE_PATH'))
    storePassword System.getenv('TREKMAP_KEYSTORE_PASSWORD')
    keyAlias System.getenv('TREKMAP_KEY_ALIAS')
    keyPassword System.getenv('TREKMAP_KEY_PASSWORD')
  }
  android.buildTypes.getByName('release').signingConfig =
       android.signingConfigs.getByName('trekmapRelease')
}
`;
 fs.writeFileSync(gradle,groovy);
}


// Brand the adaptive Android icon (no external image/font dependencies).
const drawable=path.join(root,'res/drawable');
const mipmap=path.join(root,'res/mipmap-anydpi-v26');
const values=path.join(root,'res/values');
for(const directory of [drawable,mipmap,values]) fs.mkdirSync(directory,{recursive:true});
fs.writeFileSync(path.join(values,'trekmap_colors.xml'),
  '<?xml version="1.0" encoding="utf-8"?>\n<resources><color name="trekmap_icon_bg">#0B5138</color></resources>\n');
fs.writeFileSync(path.join(drawable,'trekmap_mark.xml'),
  '<?xml version="1.0" encoding="utf-8"?>\n'+
  '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">'+
  '<path android:fillColor="#FFFFFF" android:pathData="M16,77 L40,34 L57,58 L69,44 L94,77 Z" />'+
  '<path android:fillColor="#B7E6CA" android:pathData="M27,78 Q48,67 55,83 Q67,94 83,78 L83,85 Q66,103 52,89 Q45,82 27,88 Z" />'+
  '<path android:fillColor="#FFE08F" android:pathData="M78,30 A8,8 0,1 1,77.99 30 Z" />'+
  '</vector>\n');
const adaptive='<?xml version="1.0" encoding="utf-8"?>\n'+
  '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">'+
  '<background android:drawable="@color/trekmap_icon_bg" />'+
  '<foreground android:drawable="@drawable/trekmap_mark" />'+
  '</adaptive-icon>\n';
fs.writeFileSync(path.join(mipmap,'ic_launcher.xml'),adaptive);
fs.writeFileSync(path.join(mipmap,'ic_launcher_round.xml'),adaptive);
console.log('TrekMap Android: permissions GPS natif explicite, service de localisation, HTTPS et identité graphique installés.');
