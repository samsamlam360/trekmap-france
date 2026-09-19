from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_REASONING_AGENT_UI_START -->.*?<!-- TREKMAP_REASONING_AGENT_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("TrekMap AI doit être construit avant l'interface Agent v7.")

block = r'''<!-- TREKMAP_REASONING_AGENT_UI_START -->
<style id="trekmap-reasoning-agent-css">
#tm-agent-clarify{display:none;margin:12px 0;padding:12px;border:1px solid #cfe0d7;border-radius:13px;background:#f4faf7}
#tm-agent-clarify.show{display:block}
#tm-agent-clarify h3{margin:0 0 5px;color:#1f4d3a;font-size:14px}
#tm-agent-clarify>p{margin:0 0 10px;color:#61766b;font-size:10px;line-height:1.45}
.tm-agent-q{padding:10px;margin-top:8px;border:1px solid #dde9e2;border-radius:11px;background:#fff}
.tm-agent-q label{display:block;font-size:11px;font-weight:850;color:#294f3f;margin-bottom:5px}
.tm-agent-q small{display:block;margin:-1px 0 6px;color:#778980;font-size:9px;line-height:1.35}
.tm-agent-q input{width:100%;min-height:42px;padding:9px 10px;border:1px solid #d5e2db;border-radius:10px;background:#fff;color:#203d31;outline:0}
.tm-agent-q-options{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}
.tm-agent-q-option{border:1px solid #cfe0d7;border-radius:999px;background:#fff;color:#315b49;padding:7px 9px;font-size:10px;font-weight:800}
.tm-agent-q-option.selected{background:#e1f3e9;border-color:#72b893;color:#14583d}
.tm-agent-clarify-actions{display:flex;gap:7px;margin-top:10px}
#tm-agent-continue{flex:1;min-height:42px;border:0;border-radius:10px;background:#116b49;color:#fff;font-weight:900}
#tm-agent-skip{min-height:42px;border:1px solid #d3e0d9;border-radius:10px;background:#fff;color:#526c60;font-weight:800;padding:0 10px}
#tm-agent-thinking{display:none;margin:9px 0;padding:8px 10px;border-radius:10px;background:#edf7f2;color:#466b5a;font-size:10px}
#tm-agent-thinking.show{display:block}
.tm-agent-research{margin-top:16px;padding:12px;border:1px solid #dce8e1;border-radius:13px;background:#fff}
.tm-agent-research h3{margin:0 0 8px;color:#264d3d;font-size:14px}
.tm-agent-research-meta{font-size:9px;color:#74867c;margin-bottom:8px}
.tm-agent-source{display:block;padding:8px 9px;margin:6px 0;border:1px solid #e1e9e4;border-radius:9px;text-decoration:none;background:#fafcfb;color:#205e44}
.tm-agent-source b{display:block;font-size:10px}.tm-agent-source span{display:block;margin-top:3px;color:#718279;font-size:9px;line-height:1.35}
.tm-agent-brain-badge{display:inline-flex;align-items:center;gap:5px;padding:5px 8px;border-radius:999px;background:#e9f4ff;color:#285a79;font-size:9px;font-weight:850;margin-top:7px}
@media(max-width:820px){.tm-agent-q input{font-size:16px}.tm-agent-clarify-actions{position:sticky;bottom:0;background:#f4faf7;padding-top:8px}}
</style>
<script id="trekmap-reasoning-agent-js">
(function(){
  const $=id=>document.getElementById(id);
  const endpoint=path=>(typeof API!=='undefined'?API:'')+path;
  const requestHeaders=(extra={},method='GET')=>{try{return typeof headers==='function'?headers(extra,method):extra}catch(_){return extra}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const safeUrl=v=>{try{const u=new URL(String(v||''));return ['http:','https:'].includes(u.protocol)?u.href:''}catch(_){return''}};

  const generate=$('tm-ai-generate');
  const side=document.querySelector('#tm-ai-overlay .tm-ai-side');
  if(!generate||!side)return;

  let clarify=$('tm-agent-clarify');
  if(!clarify){
    clarify=document.createElement('div');
    clarify.id='tm-agent-clarify';
    clarify.innerHTML='<h3>🧠 J’ai besoin d’une précision</h3><p id="tm-agent-understood"></p><div id="tm-agent-questions"></div><div class="tm-agent-clarify-actions"><button id="tm-agent-skip" type="button">Continuer sans préciser</button><button id="tm-agent-continue" type="button">Continuer</button></div>';
    side.insertBefore(clarify,generate);
  }
  let thinking=$('tm-agent-thinking');
  if(!thinking){
    thinking=document.createElement('div');thinking.id='tm-agent-thinking';thinking.textContent='🧠 Analyse de ta demande avant de calculer le parcours…';
    side.insertBefore(thinking,clarify);
  }

  let bypass=false,pendingPayload=null,lastClarification=null,lastAgentPlan=null;

  function payload(){
    return {
      prompt:($('tm-ai-prompt')?.value||'').trim(),
      region:($('tm-ai-region')?.value||'').trim(),
      days:Number($('tm-ai-days')?.value||3),
      daily_km:Number($('tm-ai-km')?.value||18),
      difficulty:$('tm-ai-difficulty')?.value||'medium',
      route_type:$('tm-ai-route-type')?.value||'Boucle',
      require_transit:!!$('tm-ai-transit')?.checked,
      require_water:!!$('tm-ai-water')?.checked,
      require_accommodation:!!$('tm-ai-sleep')?.checked,
      require_food:!!$('tm-ai-food')?.checked,
      current_plan:null
    };
  }

  function hideClarify(){clarify.classList.remove('show');lastClarification=null}
  function showQuestions(data){
    lastClarification=data;
    const understood=$('tm-agent-understood');
    if(understood)understood.innerHTML='<b>Ce que j’ai compris :</b> '+esc(data.understood||'Ta demande contient plusieurs possibilités.');
    const box=$('tm-agent-questions');
    box.innerHTML=(data.questions||[]).map((q,i)=>`<div class="tm-agent-q" data-q="${i}">
      <label>${esc(q.question)}</label><small>${esc(q.why||'Cette réponse peut changer le parcours.')}</small>
      ${(q.options||[]).length?`<div class="tm-agent-q-options">${q.options.map(o=>`<button type="button" class="tm-agent-q-option" data-option="${esc(o)}">${esc(o)}</button>`).join('')}</div>`:''}
      <input data-answer="${i}" placeholder="Ta réponse…" autocomplete="off">
    </div>`).join('');
    box.querySelectorAll('.tm-agent-q-option').forEach(btn=>btn.addEventListener('click',()=>{
      const parent=btn.closest('.tm-agent-q');
      parent.querySelectorAll('.tm-agent-q-option').forEach(x=>x.classList.remove('selected'));
      btn.classList.add('selected');
      const input=parent.querySelector('input');if(input)input.value=btn.dataset.option||btn.textContent||'';
    }));
    clarify.classList.add('show');
    clarify.scrollIntoView({behavior:'smooth',block:'nearest'});
  }

  function answersBlock(){
    const questions=(lastClarification&&lastClarification.questions)||[];
    const lines=[];
    questions.forEach((q,i)=>{
      const value=(clarify.querySelector(`[data-answer="${i}"]`)?.value||'').trim();
      if(value)lines.push(`- ${q.question}: ${value}`);
    });
    return lines.length?'\n\nRéponses aux questions TrekMap :\n'+lines.join('\n'):'';
  }

  async function preflight(){
    const p=payload();
    if(!p.prompt||p.prompt.length<8){
      if(typeof toast==='function')toast('Décris un peu plus le trek souhaité.');
      return;
    }
    pendingPayload=p;thinking.classList.add('show');generate.disabled=true;hideClarify();
    try{
      const r=await fetch(endpoint('/ai/clarify'),{method:'POST',headers:requestHeaders({'Content-Type':'application/json'},'POST'),body:JSON.stringify(p)});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(d.detail||'Analyse indisponible');
      if(d.needs_clarification&&(d.questions||[]).length){
        thinking.classList.remove('show');generate.disabled=false;showQuestions(d);return;
      }
    }catch(err){
      // A clarification failure must never block route planning.
      console.warn('TrekMap clarification fallback:',err);
    }
    thinking.classList.remove('show');generate.disabled=false;bypass=true;generate.click();
  }

  generate.addEventListener('click',function(ev){
    if(bypass){bypass=false;return}
    ev.preventDefault();ev.stopImmediatePropagation();preflight();
  },true);

  $('tm-agent-continue')?.addEventListener('click',()=>{
    const block=answersBlock();
    if(block&&$('tm-ai-prompt'))$('tm-ai-prompt').value=($('tm-ai-prompt').value||'').trim()+block;
    hideClarify();bypass=true;generate.click();
  });
  $('tm-agent-skip')?.addEventListener('click',()=>{hideClarify();bypass=true;generate.click()});

  // Capture the research payload without interfering with the existing AI UI.
  if(!window.__trekmapAgentFetchWrapped){
    window.__trekmapAgentFetchWrapped=true;
    const nativeFetch=window.fetch.bind(window);
    window.fetch=async function(input,init){
      const response=await nativeFetch(input,init);
      try{
        const url=typeof input==='string'?input:(input&&input.url)||'';
        if(String(url).includes('/ai/plan')){
          response.clone().json().then(data=>{
            if(data&&typeof data==='object'){lastAgentPlan=data;setTimeout(renderResearch,30)}
          }).catch(()=>{});
        }
      }catch(_){ }
      return response;
    };
  }

  function renderResearch(){
    const content=$('tm-ai-content');if(!content||!lastAgentPlan)return;
    content.querySelector('#tm-agent-research')?.remove();
    const sources=lastAgentPlan.web_sources||[];
    const agent=lastAgentPlan.agent||{};
    if(!sources.length&&!agent.brain)return;
    const section=document.createElement('div');section.className='tm-agent-research';section.id='tm-agent-research';
    const badge=agent.brain==='gemini'?'Gemini + outils TrekMap':'Moteur TrekMap local + outils Web';
    section.innerHTML=`<h3>🔎 Recherche et vérification</h3><div class="tm-agent-research-meta">${esc((lastAgentPlan.web_research||{}).queries?.length||0)} recherche(s) · ${esc((lastAgentPlan.web_research||{}).provider||'Web')}<br><span class="tm-agent-brain-badge">🧠 ${esc(badge)}</span></div>`+
      sources.slice(0,8).map(s=>{const u=safeUrl(s.url);return u?`<a class="tm-agent-source" href="${esc(u)}" target="_blank" rel="noopener"><b>${esc(s.title||'Source Web')}</b><span>${esc(s.snippet||'')}</span></a>`:''}).join('');
    content.appendChild(section);
  }

  const observer=new MutationObserver(()=>{if(lastAgentPlan)renderResearch()});
  const content=$('tm-ai-content');if(content)observer.observe(content,{childList:true,subtree:false});
})();
</script>
<!-- TREKMAP_REASONING_AGENT_UI_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekMap reasoning agent UI applied")
