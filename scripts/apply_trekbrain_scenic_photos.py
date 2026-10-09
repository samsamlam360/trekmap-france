"""Opt-in Wikimedia Commons photos of individually OSM/Wikidata-linked scenic POIs.

No photo guessed from a geographic name; no back-end or paid API calls.
Only browser-visible cards fetch limited Commons licensing and thumbnails.
"""
from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
html = path.read_text(encoding="utf-8")
html = re.sub(
    r"\s*<!-- TREKMAP_SCENIC_PHOTOS_START -->.*?<!-- TREKMAP_SCENIC_PHOTOS_END -->\s*",
    "\n", html, flags=re.S,
)
if "TREKMAP_TREKBRAIN_V91_MAP_START" not in html:
    raise SystemExit("TrekBrain v9.1 scenic photo layer must be built after the map UI")

block = r'''<!-- TREKMAP_SCENIC_PHOTOS_START -->
<script id="trekmap-scenic-photos-js">
(function(){
  "use strict";
  if(window.TrekViewPhotos)return;
  const cache=new Map();
  const CACHE_MS=12*60*60*1000;
  const MAX_LOOKUPS=10; // At most 10 remote metadata lookups per loaded page.
  let lookups=0;
  const commons='https://commons.wikimedia.org';
  const validName=name=>typeof name==='string' && name.length>4 && name.length<=180 &&
    /\.(?:jpe?g|png|webp)$/i.test(name) && !/[<>|#?\r\n]/.test(name);
  const validQ=id=>/^Q[1-9]\d{0,11}$/.test(String(id||''));
  const cleanText=value=>String(value||'')
    .replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/gi,' ')
    .replace(/&amp;/gi,'&').replace(/&quot;/gi,'"')
    .replace(/&#39;|&apos;/gi,"'").replace(/\s+/g,' ').trim().slice(0,150);
  const commonFileLink=file=>commons+'/wiki/File:'+encodeURIComponent(file.replace(/ /g,'_'));
  const safeThumb=url=>{
    try{const u=new URL(url);return u.protocol==='https:'&&
      u.hostname==='upload.wikimedia.org'?u.href:'';}catch(_){return'';}
  };
  const fetchJSON=async(url,ms=5500)=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),ms);
    try{
      const response=await fetch(url,{signal:controller.signal,credentials:'omit',mode:'cors'});
      if(!response.ok)throw Error('Média indisponible');
      return await response.json();
    }finally{clearTimeout(timer);}
  };
  async function fromWikidata(id){
    if(!validQ(id))return '';
    const url='https://www.wikidata.org/w/api.php?action=wbgetentities&props=claims&ids='+
      encodeURIComponent(id)+'&format=json&origin=*';
    const json=await fetchJSON(url);
    const statements=json.entities?.[id]?.claims?.P18||[];
    const name=statements.find(row=>row?.mainsnak?.datavalue?.value)?.mainsnak?.datavalue?.value;
    return validName(name)?name:'';
  }
  async function fetchCommons(file){
    if(!validName(file))return null;
    const url=commons+'/w/api.php?action=query&format=json&origin=*&prop=imageinfo&'+
      'iiprop=url%7Cextmetadata%7Cmime&iiurlwidth=620&titles='+
      encodeURIComponent('File:'+file);
    const json=await fetchJSON(url);
    const item=Object.values(json.query?.pages||{})[0];
    const info=item?.imageinfo?.[0],meta=info?.extmetadata||{};
    const src=safeThumb(info?.thumburl||'');
    const license=cleanText(meta.LicenseShortName?.value||'');
    if(!src||!/^image\/(jpeg|png|webp)$/i.test(info.mime||'')||!license)return null;
    return {
      src,license,
      author:cleanText(meta.Artist?.value||meta.Attribution?.value||'Auteur non précisé'),
      source:commonFileLink(file)
    };
  }
  async function resolve(file,id){
    const key=validName(file)?'F:'+file:validQ(id)?'Q:'+id:'';
    if(!key)return null;
    const cached=cache.get(key);
    if(cached && Date.now()-cached.at<CACHE_MS)return cached.data;
    if(lookups>=MAX_LOOKUPS)return null;
    lookups++;
    try{
      const exact=validName(file)?file:await fromWikidata(id);
      const data=exact?await fetchCommons(exact):null;
      cache.set(key,{data,at:Date.now()});
      return data;
    }catch(_){
      cache.set(key,{data:null,at:Date.now()});
      return null;
    }
  }
  function show(card,data){
    if(!card.isConnected)return;
    const host=card.querySelector('.tm-ux-photo-media');
    if(!host)return;
    if(!data)return; // Honest placeholder: never substitute a random landscape.
    const image=document.createElement('img');
    image.src=data.src;
    image.loading='lazy';image.decoding='async';image.referrerPolicy='no-referrer';
    image.alt='Photographie du lieu cartographié';
    image.addEventListener('error',function(){
      host.textContent='📷 Photographie temporairement indisponible';
      card.querySelector('.tm-ux-photo-credit')?.remove();
    },{once:true});
    host.replaceChildren(image);
    const credit=document.createElement('div');
    credit.className='tm-ux-photo-credit';
    credit.appendChild(document.createTextNode('Photo : '+data.author+' · '+data.license+' · '));
    const link=document.createElement('a');
    link.href=data.source;
    link.target='_blank';link.rel='noopener noreferrer';
    link.textContent='Crédits Wikimedia Commons';
    credit.appendChild(link);
    host.insertAdjacentElement('afterend',credit);
  }
  async function load(card){
    if(card.dataset.photoHydrated)return;
    card.dataset.photoHydrated='1';
    const file=card.dataset.commonsFile||'';
    const entity=card.dataset.wikidata||'';
    if(!validName(file)&&!validQ(entity))return;
    const photo=await resolve(file,entity);
    show(card,photo);
  }
  const observer=typeof IntersectionObserver==='function'
    ?new IntersectionObserver(entries=>{
      entries.forEach(entry=>{
        if(!entry.isIntersecting)return;
        observer.unobserve(entry.target);
        load(entry.target);
      });
    },{rootMargin:'180px 0px'}):null;
  function hydrate(root){
    if(!root || !root.querySelectorAll)return;
    const cards=root.querySelectorAll('.tm-ux-view-card[data-commons-file],.tm-ux-view-card[data-wikidata]');
    cards.forEach(card=>{
      if(card.dataset.photoHydrated || card.dataset.photoObserved)return;
      if(!validName(card.dataset.commonsFile)&&!validQ(card.dataset.wikidata))return;
      card.dataset.photoObserved='1';
      if(observer)observer.observe(card);
      else load(card);
    });
  }
  window.TrekViewPhotos={hydrate};
  const content=document.getElementById('tm-ai-content');
  if(content){
    const mo=new MutationObserver(()=>hydrate(content));
    mo.observe(content,{childList:true,subtree:true});
    hydrate(content);
  }
})();
</script>
<!-- TREKMAP_SCENIC_PHOTOS_END -->'''
if html.count("</body>") != 1:
    raise SystemExit("Unexpected body marker")
html=html.replace("</body>", block+"\n</body>",1)
path.write_text(html,encoding="utf-8")
print("Wikimedia view photos: lazy, source-exact, attributed, budgeted")
