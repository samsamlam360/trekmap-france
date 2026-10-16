/* TrekMap personal offline navigation. No persistent GPS uploads. */
const VERSION='tm-hike-v1';
const STATIC='tm-hike-app-v1';
const MAPS='tm-hike-tiles-v1';
const own=new URL(self.location.href).origin;
const maplibre='https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl';
function cacheable(url){
 return (url.origin===own && (url.pathname==='/randonnee'||url.pathname.startsWith('/offline-tiles/')))
     ||(url.origin==='https://unpkg.com'&&url.pathname.startsWith('/maplibre-gl@4.7.1/dist/maplibre-gl'));
}
self.addEventListener('install',event=>{self.skipWaiting()});
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 const keys=await caches.keys();
 await Promise.all(keys.filter(k=>k.startsWith('tm-hike-')&&k!==STATIC&&k!==MAPS).map(k=>caches.delete(k)));
 await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
 if(event.request.method!=='GET')return;
 const u=new URL(event.request.url);
 if(!cacheable(u))return;
 const tile=u.pathname.startsWith('/offline-tiles/');
 event.respondWith((async()=>{
   const store=await caches.open(tile?MAPS:STATIC);
   const cached=await store.match(event.request);
   if(cached)return cached;
   try{
     const response=await fetch(event.request);
     if(response.ok)await store.put(event.request,response.clone()).catch(()=>{});
     return response;
   }catch(error){
     if(cached)return cached;
     if(u.pathname==='/randonnee'){
       return new Response('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Sans réseau</title><body>Cette page n’a pas été enregistrée pour la navigation hors connexion.</body></html>',
            {headers:{'content-type':'text/html; charset=utf-8'},status:503});
     }
     throw error;
   }
 })());
});
