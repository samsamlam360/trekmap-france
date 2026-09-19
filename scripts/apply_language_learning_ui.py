from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_LANGUAGE_UI_START -->.*?<!-- TREKMAP_LANGUAGE_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("Le planificateur doit être construit avant l'interface d'apprentissage linguistique.")

block = r'''<!-- TREKMAP_LANGUAGE_UI_START -->
<style id="trekmap-language-css">
#tm-language-learn{width:100%;min-height:42px;margin-top:8px;border:1px solid #cfe0d6;border-radius:11px;background:#f8fbf9;color:#315b49;font-weight:900}
#tm-language-panel{display:none;margin-top:9px;padding:11px;border:1px solid #dce8e1;border-radius:13px;background:#f8fbf9}
#tm-language-panel.open{display:block}
.tm-language-title{font-size:12px;font-weight:900;color:#244f3c;margin-bottom:5px}
.tm-language-help{font-size:10px;line-height:1.45;color:#6a7e74;margin-bottom:9px}
.tm-language-row{display:grid;grid-template-columns:1fr 1.35fr;gap:7px}
.tm-language-row input{width:100%;min-height:40px;border:1px solid #d5e2db;border-radius:10px;padding:8px;background:#fff;color:#203d31}
#tm-language-save{width:100%;min-height:40px;margin-top:7px;border:0;border-radius:10px;background:#116b49;color:#fff;font-weight:900}
#tm-language-list{display:grid;gap:5px;margin-top:9px}
.tm-language-rule{display:flex;align-items:center;gap:7px;padding:7px 8px;border:1px solid #e0e9e4;border-radius:9px;background:#fff;font-size:10px;color:#415f52}
.tm-language-rule>span{flex:1;min-width:0}.tm-language-rule b{color:#244f3c}.tm-language-delete{width:30px;height:30px;border:0;border-radius:8px;background:#f2f5f3;color:#7b4b4b;font-weight:900}
.tm-language-empty{font-size:10px;color:#74867d;padding:4px 1px}
@media(max-width:820px){.tm-language-row{grid-template-columns:1fr}.tm-language-row input{font-size:16px}}
</style>
<script id="trekmap-language-js">
(function(){
  const side=document.querySelector('.tm-ai-side');
  if(!side||document.getElementById('tm-language-learn'))return;
  const apiBase=()=>typeof API!=='undefined'?API:'';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const reqHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const manual=document.getElementById('tm-ai-manual');
  const wrap=document.createElement('div');
  wrap.innerHTML=`<button id="tm-language-learn" type="button">🧠 Apprendre mon vocabulaire</button>
    <div id="tm-language-panel">
      <div class="tm-language-title">Apprends à TrekMap comment tu parles</div>
      <div class="tm-language-help">Exemple : <b>pépère</b> → <b>facile, max 15 km/jour et peu de dénivelé</b>. Ces règles restent liées à ton compte.</div>
      <div class="tm-language-row">
        <input id="tm-language-phrase" maxlength="80" placeholder="Expression : pépère">
        <input id="tm-language-meaning" maxlength="300" placeholder="Ça veut dire : facile, max 15 km/jour...">
      </div>
      <button id="tm-language-save" type="button">Mémoriser cette expression</button>
      <div id="tm-language-list"><div class="tm-language-empty">Chargement du vocabulaire…</div></div>
    </div>`;
  if(manual)manual.insertAdjacentElement('beforebegin',wrap);
  else side.appendChild(wrap);

  const button=document.getElementById('tm-language-learn');
  const panel=document.getElementById('tm-language-panel');
  const list=document.getElementById('tm-language-list');
  let loaded=false;

  async function loadRules(){
    list.innerHTML='<div class="tm-language-empty">Chargement du vocabulaire…</div>';
    try{
      const r=await fetch(apiBase()+'/ai/language',{headers:reqHeaders({},'GET')});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(d.detail||'Impossible de charger le vocabulaire.');
      const rules=Array.isArray(d.rules)?d.rules:[];
      if(!rules.length){list.innerHTML='<div class="tm-language-empty">Aucune expression personnelle mémorisée pour le moment.</div>';return}
      list.innerHTML=rules.map(rule=>`<div class="tm-language-rule"><span><b>${esc(rule.phrase)}</b> → ${esc(rule.meaning)}</span><button class="tm-language-delete" data-rule-id="${Number(rule.id)}" type="button" aria-label="Supprimer">×</button></div>`).join('');
    }catch(e){list.innerHTML=`<div class="tm-language-empty">${esc(e.message||'Vocabulaire indisponible')}</div>`}
  }

  button.onclick=()=>{
    panel.classList.toggle('open');
    if(panel.classList.contains('open')&&!loaded){loaded=true;loadRules()}
  };

  document.getElementById('tm-language-save').onclick=async()=>{
    const phrase=String(document.getElementById('tm-language-phrase').value||'').trim();
    const meaning=String(document.getElementById('tm-language-meaning').value||'').trim();
    if(phrase.length<2||meaning.length<2){typeof toast==='function'&&toast('Indique une expression et ce qu’elle signifie.');return}
    const btn=document.getElementById('tm-language-save');btn.disabled=true;btn.textContent='Mémorisation…';
    try{
      const r=await fetch(apiBase()+'/ai/language/learn',{method:'POST',headers:reqHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify({phrase,meaning})});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Impossible de mémoriser cette expression.');
      document.getElementById('tm-language-phrase').value='';document.getElementById('tm-language-meaning').value='';
      typeof toast==='function'&&toast(d.message||'Expression mémorisée.');await loadRules();
    }catch(e){typeof toast==='function'&&toast(e.message||'Mémorisation impossible.');}
    finally{btn.disabled=false;btn.textContent='Mémoriser cette expression'}
  };

  list.addEventListener('click',async e=>{
    const del=e.target.closest('[data-rule-id]');if(!del)return;
    const id=Number(del.dataset.ruleId);if(!id)return;
    del.disabled=true;
    try{
      const r=await fetch(apiBase()+'/ai/language/'+id,{method:'DELETE',headers:reqHeaders({},'DELETE')});
      const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||'Suppression impossible.');await loadRules();
    }catch(e){typeof toast==='function'&&toast(e.message||'Suppression impossible.');del.disabled=false}
  });
})();
</script>
<!-- TREKMAP_LANGUAGE_UI_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap language learning UI applied")
