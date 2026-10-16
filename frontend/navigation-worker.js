/* TrekMap randonnée : online-first for HTML, offline-first for saved vector tiles.
   Preserve the existing downloaded tile cache across service worker updates. */
const VERSION='tm-hike-v2-network-first';
const STATIC='tm-hike-app-v1';
const MAPS='tm-hike-tiles-v1';
const own=new URL(self.location.href).origin;
function cacheable(url){
 return (url.origin===own && (url.pathname==='/randonnee'||url.pathname.startsWith('/offline-tiles/')))
     || (url.origin==='https://unpkg.com' && url.pathname.startsWith('/maplibre-gl@4.7.1/dist/maplibre-gl'));
}
self.addEventListener('install',event=>{self.skipWaiting()});
self.addEventListener('activate',event=>event.waitUntil((async()=>{
 const keys=await caches.keys();
 await Promise.all(keys.filter(k=>k.startsWith('tm-hike-')&&k!==STATIC&&k!==MAPS).map(k=>caches.delete(k)));
 await self.clients.claim();
})()));
self.addEventListener('fetch',event=>{
 if(event.request.method!=='GET')return;
 const url=new URL(event.request.url);
 if(!cacheable(url))return;
 const page=url.origin===own && url.pathname==='/randonnee';
 const tile=url.origin===own && url.pathname.startsWith('/offline-tiles/');
 event.respondWith((async()=>{
   const store=await caches.open(tile?MAPS:STATIC);
   // Use a single canonical copy of the page, regardless of the cache-buster query.
   const cacheKey=page?new URL('/randonnee',own).href:event.request;
   const cached=await store.match(cacheKey);
   if(!page && cached)return cached;
   try{
     // Force the real current page to be fetched while online; never serve stale
     // HTML indefinitely. Workers fetch independently of this fetch handler.
     const response=await fetch(page?new Request(event.request,{cache:'no-store'}):event.request);
     if(response.ok){
       await store.put(cacheKey,response.clone()).catch(()=>{});
       return response;
     }
     if(cached)return cached;
     return response;
   }catch(err){
     if(cached)return cached;
     if(page)return new Response('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Sans réseau</title><body>Ce trek n’est pas encore disponible hors connexion.</body></html>',
         {headers:{'content-type':'text/html; charset=utf-8'},status:503});
     throw err;
   }
 })());
});
