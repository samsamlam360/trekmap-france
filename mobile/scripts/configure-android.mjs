// Configure the freshly generated Capacitor 8 Android shell.
// Only foreground geolocation is declared. Background tracking comes in a separate, audited phase.
import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve('android/app/src/main');
const manifest=path.join(root,'AndroidManifest.xml');
if(!fs.existsSync(manifest)) throw Error('Projet natif absent : lance npm run android:add');
let xml=fs.readFileSync(manifest,'utf8');
if(!xml.includes('<manifest') || !xml.includes('<application')) throw Error('AndroidManifest.xml inattendu');
for(const permission of ['android.permission.INTERNET','android.permission.ACCESS_COARSE_LOCATION','android.permission.ACCESS_FINE_LOCATION']){
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
fs.writeFileSync(manifest,xml);

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
console.log('TrekMap Android: permissions GPS au premier plan, HTTPS uniquement, identité graphique installées.');
