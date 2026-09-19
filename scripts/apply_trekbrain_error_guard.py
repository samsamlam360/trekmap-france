"""Harden TrekBrain's request payload and FastAPI error rendering.

FastAPI validation errors use structured ``detail`` arrays. Passing such an
array directly to ``Error`` turns it into the useless ``[object Object]`` text.
This build patch keeps the existing planner UI intact while normalising form
values and rendering validation failures as readable French messages.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

MARKER = "TREKMAP_API_ERROR_GUARD_V92"
if MARKER in html:
    print("TrekBrain API error guard already applied")
    raise SystemExit(0)

anchor = "  const difficultyLabel={easy:'Facile',medium:'Moyen',hard:'Difficile'};"
helper = r'''  // TREKMAP_API_ERROR_GUARD_V92
  const fieldLabel={prompt:'demande',region:'région',days:'jours',daily_km:'km / jour',difficulty:'difficulté',route_type:'type de parcours',require_transit:'transports',require_water:'eau',require_accommodation:'nuitées',require_food:'ravitaillement',current_plan:'parcours actuel'};
  const boundedNumber=(value,fallback,min,max,integer=false)=>{
    const parsed=Number(value);const safe=Number.isFinite(parsed)?parsed:fallback;
    const bounded=Math.max(min,Math.min(max,safe));
    return integer?Math.round(bounded):Math.round(bounded*10)/10;
  };
  const apiErrorMessage=(data,status)=>{
    const detail=data&&data.detail;
    if(Array.isArray(detail)){
      const rows=detail.map(err=>{
        if(!err||typeof err!=='object')return String(err||'').trim();
        const loc=Array.isArray(err.loc)?err.loc.filter(x=>x!=='body').map(x=>fieldLabel[x]||String(x)).join(' → '):'';
        const msg=String(err.msg||err.message||'Valeur invalide').trim();
        return loc?`${loc} : ${msg}`:msg;
      }).filter(Boolean);
      if(rows.length)return rows.join(' • ');
    }
    if(detail&&typeof detail==='object'){
      if(typeof detail.message==='string'&&detail.message.trim())return detail.message.trim();
      if(typeof detail.msg==='string'&&detail.msg.trim())return detail.msg.trim();
      try{const encoded=JSON.stringify(detail);if(encoded&&encoded!=='{}')return encoded}catch(_){}
    }
    if(typeof detail==='string'&&detail.trim())return detail.trim();
    if(data&&typeof data.message==='string'&&data.message.trim())return data.message.trim();
    return `La préparation du trek a échoué${status?` (HTTP ${status})`:''}.`;
  };'''

if anchor not in html:
    raise SystemExit("Ancre TrekMap AI introuvable pour le garde d'erreurs.")
html = html.replace(anchor, anchor + "\n" + helper, 1)

old_payload = r'''      prompt:refineText||basePrompt,
      region:String($('tm-ai-region').value||'').trim(),
      days:Number($('tm-ai-days').value||3),
      daily_km:Number($('tm-ai-km').value||18),
      difficulty:$('tm-ai-difficulty').value,
      route_type:$('tm-ai-route-type').value,'''
new_payload = r'''      prompt:String(refineText||basePrompt).trim().slice(0,4000),
      region:String($('tm-ai-region').value||'').trim().slice(0,120),
      days:boundedNumber($('tm-ai-days').value,3,1,21,true),
      daily_km:boundedNumber($('tm-ai-km').value,18,3,40,false),
      difficulty:['easy','medium','hard'].includes($('tm-ai-difficulty').value)?$('tm-ai-difficulty').value:'medium',
      route_type:String($('tm-ai-route-type').value||'Boucle').trim().slice(0,30),'''
if old_payload not in html:
    raise SystemExit("Le format du payload TrekMap AI a changé ; correctif V9.2 à revoir.")
html = html.replace(old_payload, new_payload, 1)

error_candidates = [
    "      if(!r.ok)throw new Error(d.detail||'La préparation IA a échoué.');",
    "      if(!r.ok)throw new Error(d.detail||'La préparation du trek a échoué.');",
]
new_error = "      if(!r.ok)throw new Error(apiErrorMessage(d,r.status));"
for old_error in error_candidates:
    if old_error in html:
        html = html.replace(old_error, new_error, 1)
        break
else:
    raise SystemExit("La gestion d'erreur TrekMap AI a changé ; correctif V9.2 à revoir.")

html_path.write_text(html, encoding="utf-8")
print("TrekBrain API validation/error guard applied")
