// Copy a pinned and locally available MapLibre build into the APK.
// The offline screen must not fetch any JavaScript, CSS, sprite, font or tile from the Internet.
import fs from 'node:fs';
import path from 'node:path';
const dist=path.resolve('node_modules/maplibre-gl/dist');
const target=path.resolve('www/vendor');
fs.mkdirSync(target,{recursive:true});
for(const file of ['maplibre-gl.js','maplibre-gl.css']) {
 const src=path.join(dist,file);
 if(!fs.existsSync(src))throw Error('Missing pinned maplibre-gl dependency: '+src);
 const out=path.join(target,file);
 fs.copyFileSync(src,out);
 if(fs.statSync(out).size<1000)throw Error('Incomplete '+file);
 console.log('Bundled offline: '+file+' ('+fs.statSync(out).size+' bytes)');
}
