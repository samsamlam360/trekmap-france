"""Show structured TrekBrain v9 failure diagnostics on the mobile error screen."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_ERROR_DIAGNOSTICS_V95_START -->.*?<!-- TREKMAP_ERROR_DIAGNOSTICS_V95_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_FAILURE_ACTIONS_V93_START" not in html:
    raise SystemExit("Les actions d'échec TrekBrain doivent être construites avant le diagnostic.")

block = r'''<!-- TREKMAP_ERROR_DIAGNOSTICS_V95_START -->
<style id="trekmap-error-diagnostics-v95-css">
.tm-ai-diagnostic{margin:0 0 12px;padding:11px;border:1px solid #d7dfe9;border-radius:12px;background:#f7f9fc;color:#263548}
.tm-ai-diagnostic-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.tm-ai-diagnostic-head strong{font-size:12px}
.tm-ai-diagnostic-code{display:inline-flex;align-items:center;max-width:100%;padding:5px 8px;border-radius:8px;background:#1f2937;color:#fff;font:900 11px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.2px;overflow-wrap:anywhere}
.tm-ai-diagnostic-grid{display:grid;grid-template-columns:auto 1fr;gap:5px 9px;font-size:10px;line-height:1.4}
.tm-ai-diagnostic-grid b{color:#617086}.tm-ai-diagnostic-grid span{color:#263548;overflow-wrap:anywhere}
.tm-ai-diagnostic-next{margin-top:8px;padding:8px;border-radius:9px;background:#eef3f8;font-size:10px;line-height:1.45;color:#42536a}
.tm-ai-diagnostic-copy{margin-top:8px;width:100%;border:1px solid #cad5e2;border-radius:9px;background:#fff;color:#334155;padding:8px;font-size:10px;font-weight:900;cursor:pointer}
@media(max-width:520px){.tm-ai-diagnostic{padding:10px}.tm-ai-diagnostic-grid{grid-template-columns:88px 1fr}}
</style>
<script id="trekmap-error-diagnostics-v95-js">
(function(){
  if(window.__trekmapErrorDiagnosticsV95)return;window.__trekmapErrorDiagnosticsV95=true;
  let latest=null;
  const $=id=>document.getElementById(id);
  const clean=value=>String(value??'').trim();

  function payloadFrom(data,status){
    const detail=data&&data.detail;
    if(!detail||typeof detail!=='object')return null;
    const diagnostic=detail.diagnostic&&typeof detail.diagnostic==='object'?detail.diagnostic:null;
    if(!diagnostic)return null;
    return {
      diagnostic,
      effective:detail.effective_request&&typeof detail.effective_request==='object'?detail.effective_request:null,
      resolution:detail.request_resolution&&typeof detail.request_resolution==='object'?detail.request_resolution:null,
      message:clean(detail.message||''),
      responseStatus:Number(status)||null
    };
  }

  function addRow(grid,label,value){
    if(value===undefined||value===null||value==='')return;
    const key=document.createElement('b');key.textContent=label;
    const val=document.createElement('span');val.textContent=String(value);
    grid.append(key,val);
  }

  function interpretation(payload){
    const e=payload?.effective||{};
    const parts=[];
    if(clean(e.region))parts.push(clean(e.region));
    if(clean(e.route_type))parts.push(clean(e.route_type));
    if(Number.isFinite(Number(e.days)))parts.push(`${Number(e.days)} j`);
    if(Number.isFinite(Number(e.daily_km)))parts.push(`${Number(e.daily_km)} km/j`);
    return parts.join(' · ');
  }

  function diagnosticText(payload){
    if(!payload)return '';
    const d=payload.diagnostic||{};
    return [
      `Code: ${clean(d.code)||'inconnu'}`,
      `Diagnostic ID: ${clean(d.id)||'inconnu'}`,
      `Étape: ${clean(d.stage)||'inconnue'}`,
      `Service: ${clean(d.service)||'inconnu'}`,
      `HTTP API: ${d.api_status??payload.responseStatus??'n/a'}`,
      `HTTP fournisseur: ${d.provider_http_status??'n/a'}`,
      `Réessayable: ${d.retryable?'oui':'non'}`,
      `Aperçu disponible: ${d.preview_available?'oui':'non'}`,
      `Interprétation: ${interpretation(payload)||'n/a'}`,
      `Message: ${payload.message||'n/a'}`,
      `À vérifier: ${clean(d.next_check)||'n/a'}`
    ].join('\n');
  }

  async function copyDiagnostic(){
    const text=diagnosticText(latest);
    if(!text)return;
    try{
      await navigator.clipboard.writeText(text);
      if(typeof toast==='function')toast('Diagnostic TrekBrain copié.');
    }catch(_){
      if(typeof toast==='function')toast('Copie automatique impossible. Fais une capture du diagnostic.');
    }
  }

  function render(){
    if(!latest)return;
    const host=$('tm-ai-failure-actions');
    if(!host||host.querySelector('#tm-ai-diagnostic'))return;
    const d=latest.diagnostic||{};
    const box=document.createElement('section');box.id='tm-ai-diagnostic';box.className='tm-ai-diagnostic';

    const head=document.createElement('div');head.className='tm-ai-diagnostic-head';
    const title=document.createElement('strong');title.textContent='🔧 Diagnostic technique';
    const code=document.createElement('span');code.className='tm-ai-diagnostic-code';code.textContent=clean(d.code)||'TB-PLAN-UNKNOWN';
    head.append(title,code);box.appendChild(head);

    const grid=document.createElement('div');grid.className='tm-ai-diagnostic-grid';
    addRow(grid,'Étape',clean(d.stage));
    addRow(grid,'Service',clean(d.service));
    addRow(grid,'HTTP API',d.api_status??latest.responseStatus);
    addRow(grid,'HTTP service',d.provider_http_status);
    addRow(grid,'Réessayable',d.retryable?'Oui':'Non');
    addRow(grid,'Aperçu',d.preview_available?'Disponible':'Non disponible');
    addRow(grid,'Demande comprise',interpretation(latest));
    addRow(grid,'ID',clean(d.id));
    box.appendChild(grid);

    if(clean(d.next_check)){
      const next=document.createElement('div');next.className='tm-ai-diagnostic-next';
      next.textContent='À vérifier : '+clean(d.next_check);box.appendChild(next);
    }
    const copy=document.createElement('button');copy.id='tm-ai-diagnostic-copy';copy.type='button';copy.className='tm-ai-diagnostic-copy';copy.textContent='📋 Copier le diagnostic';
    copy.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();copyDiagnostic()});
    box.appendChild(copy);
    host.insertBefore(box,host.firstChild);
  }

  const previous=window.fetch.bind(window);
  window.fetch=async function(input,init){
    const response=await previous(input,init);
    try{
      const url=String(typeof input==='string'?input:(input&&input.url)||'');
      if(url.includes('/ai/plan')){
        if(response.ok){latest=null}
        else response.clone().json().then(data=>{
          latest=payloadFrom(data,response.status);
          if(latest){setTimeout(render,70);setTimeout(render,260)}
        }).catch(()=>{});
      }
    }catch(_){}
    return response;
  };

  const content=$('tm-ai-content');
  if(content)new MutationObserver(()=>{if(latest)setTimeout(render,20)}).observe(content,{childList:true,subtree:true});
})();
</script>
<!-- TREKMAP_ERROR_DIAGNOSTICS_V95_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain failure diagnostics UI applied")
