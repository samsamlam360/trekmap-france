from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

replacement = r'''
  const gpxInput=$('gpx-file');
  if(gpxInput){
    const fresh=gpxInput.cloneNode(true);
    gpxInput.replaceWith(fresh);
    window.importGPX=function(){
      if(!currentUserSafe()){authModal('login');return}
      fresh.value='';
      fresh.click();
    };
    fresh.addEventListener('change',()=>{
      const file=fresh.files?.[0];
      if(!file)return;
      if(!/\.gpx$/i.test(file.name)){toast?.('Choisis un fichier GPX.');return}
      openModal(`<div class="modal-head"><div><h2>Importer un trek</h2><div style="color:#6c7e76;font-size:11px">${esc(file.name)} · ${(file.size/1024/1024).toFixed(2)} Mo</div></div><button class="close" id="modal-close">✕</button></div><p style="color:#61746b;font-size:12px">Le trek sera d'abord privé. Tu pourras ensuite compléter ses informations et le publier.</p><div class="modal-actions"><button class="ghost-btn" id="tm-gpx-cancel">Annuler</button><button class="primary-btn" id="tm-gpx-confirm">Importer</button></div>`);
      $('modal-close').onclick=closeModal;
      $('tm-gpx-cancel').onclick=closeModal;
      $('tm-gpx-confirm').onclick=async()=>{
        const b=$('tm-gpx-confirm');
        b.disabled=true;
        b.textContent='Import…';
        try{
          const fd=new FormData();
          fd.append('file',file);
          const r=await fetch(api()+'/upload-gpx',{method:'POST',headers:authHeaders({},'POST'),body:fd});
          const d=await r.json();
          if(!r.ok)throw new Error(d.detail||'Import impossible');
          closeModal();
          await loadTraces();
          criteriaReady=false;
          await loadCriteria(true);
          applyUnifiedFilters();
          setTimeout(()=>openEdit(Number(d.id)),100);
          toast?.(d.message||'GPX importé.');
        }catch(e){
          b.disabled=false;
          b.textContent='Importer';
          toast?.(e.message||'Import impossible.');
        }
      };
    });
  }

  // Accueil unifié.'''

html, count = re.subn(
    r"\n  const gpxInput=\$\('gpx-file'\);.*?\n\n  // Accueil unifié\.",
    replacement,
    html,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit("Bloc d'import GPX unifié introuvable")

html_path.write_text(html, encoding="utf-8")
print("TrekMap unified build finalized")
