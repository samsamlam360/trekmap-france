from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r'\s*<!-- TREKMAP_TARGET_LAYOUT_START -->.*?<!-- TREKMAP_TARGET_LAYOUT_END -->\s*',
    '\n',
    html,
    flags=re.S,
)

block = r'''<!-- TREKMAP_TARGET_LAYOUT_START -->
<style id="trekmap-target-layout-css">
:root{--tm-topbar-h:82px;--tm-panel-w:408px}
html,body{height:100%;overflow:hidden!important}
#app{height:100vh!important;padding-top:var(--tm-topbar-h)!important;background:#eef5f1!important}
#map,.sidebar{height:calc(100vh - var(--tm-topbar-h))!important}

/* Barre principale */
#tm-explorer-topbar{position:absolute!important;top:0!important;left:0!important;right:0!important;height:var(--tm-topbar-h)!important;z-index:6000!important;padding:8px 28px!important;display:grid!important;grid-template-columns:minmax(290px,360px) minmax(320px,520px) 1fr!important;align-items:center!important;gap:28px!important;background:linear-gradient(105deg,#074a34 0%,#0a5c40 48%,#064832 100%)!important;box-shadow:0 9px 28px rgba(5,43,29,.24)!important;overflow:hidden!important}
#tm-explorer-topbar:before{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(135deg,transparent 0 18%,rgba(255,255,255,.035) 18% 19%,transparent 19% 100%),radial-gradient(circle at 24% 130%,rgba(255,255,255,.13),transparent 34%)}
.tm-explorer-logo{position:relative!important;z-index:1!important;width:100%!important;min-width:0!important;height:66px!important;padding:0!important;border:0!important;background:transparent!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;border-radius:15px!important;overflow:hidden!important}
.tm-explorer-logo:hover{background:rgba(255,255,255,.07)!important}
.tm-explorer-logo img{width:330px!important;max-width:100%!important;height:64px!important;max-height:64px!important;object-fit:contain!important;object-position:left center!important;border-radius:0!important}
.tm-top-search{position:relative!important;z-index:1!important;width:100%!important;max-width:none!important;margin:0!important;height:50px!important;background:#fff!important;border:1px solid rgba(255,255,255,.65)!important;border-radius:999px!important;box-shadow:0 8px 24px rgba(0,0,0,.14)!important;display:flex!important;align-items:center!important;overflow:hidden!important}
.tm-top-search span{padding-left:18px!important;font-size:19px!important;color:#315a49!important}.tm-top-search input{height:100%!important;width:100%!important;border:0!important;outline:0!important;background:transparent!important;padding:0 18px 0 10px!important;font-size:14px!important;color:#17372b!important}
.tm-top-search input::placeholder{color:#75867e!important}
.tm-top-actions{position:relative!important;z-index:1!important;margin:0!important;display:flex!important;justify-content:flex-end!important;align-items:center!important;gap:10px!important;min-width:0!important}
.tm-top-actions button{height:46px!important;border-radius:999px!important;border:1px solid rgba(255,255,255,.50)!important;background:rgba(255,255,255,.07)!important;color:#fff!important;padding:0 17px!important;font-weight:800!important;display:flex!important;align-items:center!important;justify-content:center!important;gap:8px!important;white-space:nowrap!important;box-shadow:none!important;transition:.16s!important}
.tm-top-actions button:hover{background:rgba(255,255,255,.15)!important;transform:translateY(-1px)!important}
#tm-top-explore{background:linear-gradient(135deg,#15925e,#22aa72)!important;border-color:#33ba81!important;box-shadow:0 8px 18px rgba(4,48,31,.22)!important}
#tm-top-create{background:rgba(7,61,43,.56)!important}
#tm-top-notify{width:46px!important;padding:0!important;font-size:18px!important;border-color:transparent!important;background:transparent!important}
#tm-top-account{padding:0 10px 0 7px!important;border-color:transparent!important;background:transparent!important}
.tm-top-avatar{width:36px!important;height:36px!important;border-radius:50%!important;background:#159564!important;color:#fff!important;display:grid!important;place-items:center!important;font-weight:900!important;border:1px solid rgba(255,255,255,.22)!important}
#tm-top-account-name{max-width:120px!important;overflow:hidden!important;text-overflow:ellipsis!important}

/* Panneau gauche comme la maquette */
.sidebar{width:var(--tm-panel-w)!important;min-width:var(--tm-panel-w)!important;padding:14px 14px 16px!important;background:rgba(245,250,247,.98)!important;border-right:1px solid #d5e4dc!important;box-shadow:12px 0 34px rgba(10,49,33,.11)!important;overflow:hidden!important;display:flex!important;flex-direction:column!important;gap:12px!important}
.sidebar.collapsed{margin-left:calc(-1 * var(--tm-panel-w))!important}
#sidebar .brand,#sidebar .account,#sidebar .tabs,#sidebar .list-head,#sidebar #trek-list{display:none!important}
.search-wrap{position:relative!important;flex:0 0 auto!important;margin:0!important;padding:61px 14px 15px!important;background:#fff!important;border:1px solid #d9e7df!important;border-radius:20px!important;box-shadow:0 8px 24px rgba(16,57,38,.075)!important}
.search-wrap:before{content:"▣   Rechercher un trek"!important;position:absolute!important;left:18px!important;top:18px!important;color:#153c2d!important;font-size:15px!important;font-weight:900!important;letter-spacing:-.01em!important}
.search-wrap:after{content:"⌃";position:absolute;right:18px;top:17px;color:#47675a;font-size:16px;font-weight:900}
.search{height:46px!important;border:1px solid #d5e3dc!important;border-radius:13px!important;background:#fbfdfc!important;padding:0 42px 0 43px!important;font-size:13px!important;box-shadow:0 2px 7px rgba(12,50,33,.035)!important}
.search-wrap .search:focus{background:#fff!important;border-color:#58a980!important;box-shadow:0 0 0 4px rgba(38,155,105,.10)!important}
.search-wrap:has(.search):focus-within:before{color:#176b45!important}
.search-wrap .clear-search{right:23px!important;top:72px!important;color:#7d8d85!important}
.search-wrap .suggestions{left:14px!important;right:14px!important;top:112px!important;border-radius:14px!important;box-shadow:0 15px 36px rgba(11,48,31,.16)!important}
.search-wrap .search{background-image:linear-gradient(transparent,transparent)!important}
.filters{position:relative!important;flex:1 1 auto!important;min-height:0!important;margin:0!important;padding:58px 14px 16px!important;background:#fff!important;border:1px solid #d9e7df!important;border-radius:20px!important;box-shadow:0 8px 24px rgba(16,57,38,.075)!important;overflow:auto!important}
.filters:before{content:"☷   Filtres"!important;position:absolute!important;left:18px!important;top:18px!important;color:#153c2d!important;font-size:15px!important;font-weight:900!important}
.filters:after{content:"⌃";position:absolute;right:18px;top:17px;color:#47675a;font-size:16px;font-weight:900}
.filters::-webkit-scrollbar{width:6px}.filters::-webkit-scrollbar-thumb{background:#b8c9c0;border-radius:99px}.filters::-webkit-scrollbar-track{background:transparent}
.filter-row{gap:12px!important}.field label{font-size:10px!important;text-transform:none!important;letter-spacing:.01em!important;color:#415f52!important;font-weight:850!important;margin:9px 0 6px!important}.field select,.field input{border:1px solid #d8e5de!important;border-radius:12px!important;background:#fff!important;min-height:42px!important;box-shadow:0 2px 7px rgba(13,50,34,.025)!important}.field select:focus,.field input:focus{outline:none!important;border-color:#5ca77f!important;box-shadow:0 0 0 3px rgba(38,155,105,.09)!important}
input[type=range]{accent-color:#16895a!important}
.filter-actions{display:grid!important;grid-template-columns:1fr 1fr!important;gap:9px!important;margin-top:16px!important}.filter-actions button{min-height:43px!important;border-radius:12px!important;font-weight:850!important}.filter-actions #reset-filters{order:1!important;background:#f5f8f6!important;color:#65766e!important;border:1px solid #dce7e1!important}.filter-actions #tm-filter-search{order:2!important;background:linear-gradient(135deg,#168b59,#1ea66b)!important;color:#fff!important;border:0!important;box-shadow:0 7px 16px rgba(22,139,89,.20)!important}.filter-actions #upload-button{order:3!important;grid-column:1/-1!important;min-height:36px!important;background:#eef7f2!important;color:#176b45!important;border:1px solid #d7eadf!important;font-size:11px!important}.filter-actions #create-button{display:none!important}

/* Menu carte façon carte de contrôle, jamais hors écran */
.map-tools{position:absolute!important;left:auto!important;right:18px!important;top:16px!important;z-index:2800!important;display:block!important;max-width:260px!important}
#tm-map-options{width:206px!important;min-width:206px!important;height:64px!important;padding:9px 12px 9px 48px!important;border:1px solid #d7e5dd!important;border-radius:16px!important;background:rgba(255,255,255,.97)!important;box-shadow:0 10px 28px rgba(14,49,33,.15)!important;color:#173d2e!important;font-weight:900!important;text-align:left!important;position:relative!important;line-height:1.05!important}
#tm-map-options:before{content:"🗺";position:absolute;left:15px;top:18px;font-size:23px}
#tm-map-options:after{content:"OpenStreetMap   ⌄";display:block;margin-top:7px;font-size:11px;font-weight:700;color:#5c7066}
#tm-map-options:hover{transform:translateY(-1px)!important;box-shadow:0 13px 32px rgba(14,49,33,.19)!important}
#tm-map-options-panel{position:absolute!important;top:72px!important;left:auto!important;right:0!important;width:236px!important;max-width:calc(100vw - 36px)!important;max-height:280px!important;overflow:auto!important;background:rgba(255,255,255,.98)!important;border:1px solid #d5e4dc!important;border-radius:17px!important;box-shadow:0 18px 44px rgba(12,47,31,.22)!important;padding:11px!important}
#tm-map-options-panel label{font-size:10px!important;color:#65776e!important;font-weight:900!important;letter-spacing:.04em!important}#tm-map-options-panel button,#tm-map-options-panel select{width:100%!important;min-height:40px!important;margin:0 0 7px!important;border-radius:11px!important;border:1px solid #dce7e1!important;background:#fff!important;padding:8px 10px!important}

/* Actions à droite, assez loin du menu carte */
#tm-side-actions{right:18px!important;top:282px!important;bottom:auto!important;transform:none!important;display:flex!important;flex-direction:column!important;gap:11px!important;z-index:2400!important}
#tm-side-actions button{width:78px!important;min-height:78px!important;border-radius:20px!important;background:rgba(255,255,255,.96)!important;border:1px solid #d8e6df!important;box-shadow:0 10px 26px rgba(14,50,34,.15)!important;color:#315548!important;padding:8px 5px!important}
#tm-side-actions button:hover{transform:translateX(-3px)!important;border-color:#95c3a9!important;box-shadow:0 14px 32px rgba(14,50,34,.20)!important}.tm-action-icon{width:34px!important;height:34px!important;border-radius:11px!important;background:linear-gradient(145deg,#eef8f2,#dff1e7)!important;color:#176b45!important;display:grid!important;place-items:center!important;font-size:18px!important}.tm-side-actions button b{font-size:11px!important}.tm-side-actions button small{font-size:9px!important;color:#7a8a82!important}
body.tm-map-menu-open #tm-side-actions{top:430px!important}

/* Barre de treks horizontale */
#tm-results-drawer{left:calc(var(--tm-panel-w) + 18px)!important;right:18px!important;bottom:14px!important;z-index:2300!important}
#tm-results-drawer.tm-open{height:184px!important}#tm-results-drawer.tm-collapsed{height:45px!important}
#tm-results-drawer .tm-results-shell{background:rgba(252,254,253,.97)!important;backdrop-filter:blur(18px)!important;border:1px solid #d7e5dd!important;border-radius:23px!important;box-shadow:0 15px 42px rgba(14,51,34,.18)!important;overflow:hidden!important}
#tm-results-drawer .tm-results-handle{height:45px!important;padding:0 18px!important}.tm-results-grip{width:38px!important;height:4px!important;background:#a8bbb1!important}.tm-results-title{font-size:13px!important;font-weight:900!important;color:#183c2d!important}.tm-results-count{background:#e8f5ed!important;border:1px solid #d4eadf!important;color:#176b45!important}.tm-results-chevron{margin-left:auto!important;width:29px!important;height:29px!important;border-radius:9px!important;background:#e9f5ee!important;color:#176b45!important;display:grid!important;place-items:center!important}
#tm-results-drawer .tm-results-track{height:139px!important;padding:3px 14px 13px!important;gap:13px!important;overflow-x:auto!important;overflow-y:hidden!important}
#tm-results-drawer .tm-result-card{flex:0 0 285px!important;height:123px!important;border-radius:16px!important;border:1px solid #dfeae4!important;background:#fff!important;box-shadow:0 4px 14px rgba(17,59,40,.065)!important;padding:13px!important}#tm-results-drawer .tm-result-card:hover{transform:translateY(-2px)!important;border-color:#99c6ac!important;box-shadow:0 10px 25px rgba(17,59,40,.12)!important}
#bottom-nav{display:none!important}

@media(max-width:1180px){#tm-explorer-topbar{grid-template-columns:260px minmax(260px,1fr) auto!important;gap:14px!important}.tm-explorer-logo img{width:250px!important}.tm-top-actions button{padding:0 12px!important}.tm-top-actions #tm-top-account-name{display:none!important}}
@media(max-width:900px){:root{--tm-topbar-h:68px;--tm-panel-w:min(410px,94vw)}#tm-explorer-topbar{height:68px!important;padding:7px 9px!important;grid-template-columns:52px 1fr auto!important;gap:7px!important}.tm-explorer-logo{height:52px!important}.tm-explorer-logo img{width:52px!important;height:50px!important;object-fit:cover!important;object-position:left!important}.tm-top-search{height:44px!important}.tm-top-actions{gap:4px!important}.tm-top-actions button{width:40px!important;height:40px!important;padding:0!important}.tm-top-actions .tm-top-label,#tm-top-account-name,#tm-top-notify{display:none!important}.sidebar{width:min(410px,94vw)!important;min-width:0!important}.sidebar.collapsed{margin-left:calc(-1 * min(410px,94vw))!important}.map-tools{right:10px!important;top:10px!important}#tm-map-options{width:164px!important;min-width:164px!important;height:56px!important}#tm-side-actions{right:10px!important;top:auto!important;bottom:195px!important}body.tm-map-menu-open #tm-side-actions{top:auto!important;bottom:195px!important}#tm-results-drawer{left:10px!important;right:10px!important;bottom:10px!important}.filter-row{grid-template-columns:1fr!important}}
</style>
<script id="trekmap-target-layout-js">
(function(){
  const app=document.getElementById('app');
  if(!app)return;

  function ensureTopbar(){
    let bar=document.getElementById('tm-explorer-topbar');
    if(!bar){bar=document.createElement('header');bar.id='tm-explorer-topbar';app.prepend(bar);}
    bar.innerHTML='<button class="tm-explorer-logo" id="tm-explorer-home" type="button" title="Retour à l’accueil"><img src="/logo-trekmap.svg" alt="TrekMap France"></button><label class="tm-top-search"><span aria-hidden="true">⌕</span><input id="tm-top-search-input" type="search" autocomplete="off" placeholder="Rechercher un trek, une région, un lieu…" aria-label="Rechercher un trek"></label><div class="tm-top-actions"><button id="tm-top-explore" type="button">🗺 <span class="tm-top-label">Explorer</span></button><button id="tm-top-create" type="button">⌘ <span class="tm-top-label">Créer un trek</span></button><button id="tm-top-notify" type="button" title="Notifications">♧</button><button id="tm-top-account" type="button"><span class="tm-top-avatar" id="tm-top-avatar">S</span><span id="tm-top-account-name">Compte</span>⌄</button></div>';
  }
  ensureTopbar();

  const leftSearch=document.getElementById('search');
  const topSearch=document.getElementById('tm-top-search-input');
  let syncing=false;
  function toTop(){if(syncing||!leftSearch||!topSearch)return;syncing=true;topSearch.value=leftSearch.value||'';syncing=false;}
  function toLeft(){if(syncing||!leftSearch||!topSearch)return;syncing=true;leftSearch.value=topSearch.value;leftSearch.dispatchEvent(new Event('input',{bubbles:true}));syncing=false;}
  topSearch?.addEventListener('input',toLeft);leftSearch?.addEventListener('input',toTop);toTop();
  topSearch?.addEventListener('keydown',e=>{if(e.key==='Enter'){toLeft();document.getElementById('tm-results-drawer')?.classList.add('tm-open');document.getElementById('tm-results-drawer')?.classList.remove('tm-collapsed');}});

  document.getElementById('tm-explorer-home')?.addEventListener('click',()=>{
    if(typeof window.TrekMapShowHome==='function')window.TrekMapShowHome();
    else document.getElementById('tm-home')?.classList.remove('tm-hidden');
  });
  document.getElementById('tm-top-explore')?.addEventListener('click',()=>{
    document.getElementById('tm-home')?.classList.add('tm-hidden');
    document.querySelector('.tab[data-tab="all"]')?.click();
    document.getElementById('sidebar')?.classList.remove('collapsed');
  });
  document.getElementById('tm-top-create')?.addEventListener('click',()=>document.getElementById('create-button')?.click());
  document.getElementById('tm-top-account')?.addEventListener('click',()=>document.getElementById('account-button')?.click());
  document.getElementById('tm-top-notify')?.addEventListener('click',()=>{if(typeof toast==='function')toast('Aucune nouvelle notification.');});

  function syncAccount(){
    const name=(document.getElementById('account-name')?.textContent||'Compte').trim();
    const display=name==='Mode visiteur'?'Connexion':name;
    const n=document.getElementById('tm-top-account-name'),a=document.getElementById('tm-top-avatar');
    if(n)n.textContent=display;if(a)a.textContent=(display||'C').slice(0,1).toUpperCase();
  }
  syncAccount();
  const sourceName=document.getElementById('account-name');if(sourceName)new MutationObserver(syncAccount).observe(sourceName,{childList:true,subtree:true,characterData:true});

  const actions=document.querySelector('.filter-actions');
  if(actions&&!document.getElementById('tm-filter-search')){
    const b=document.createElement('button');b.id='tm-filter-search';b.type='button';b.textContent='⌕  Rechercher';
    b.addEventListener('click',()=>{if(typeof applyFilters==='function')applyFilters();document.getElementById('tm-results-drawer')?.classList.add('tm-open');document.getElementById('tm-results-drawer')?.classList.remove('tm-collapsed');});
    actions.appendChild(b);
  }

  const options=document.getElementById('tm-map-options'),panel=document.getElementById('tm-map-options-panel');
  if(options){options.textContent='Type de carte';options.setAttribute('title','Options de la carte');}
  options?.addEventListener('click',()=>setTimeout(()=>document.body.classList.toggle('tm-map-menu-open',!!panel?.classList.contains('tm-show')),0));
  document.addEventListener('click',e=>{if(panel&&!panel.contains(e.target)&&e.target!==options)document.body.classList.remove('tm-map-menu-open');});
  panel?.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>document.body.classList.remove('tm-map-menu-open')));
})();
</script>
<!-- TREKMAP_TARGET_LAYOUT_END -->'''

html = html.replace('</body>', block + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap target layout applied')
