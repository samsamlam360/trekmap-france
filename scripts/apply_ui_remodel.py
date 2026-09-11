from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / 'frontend' / 'index.html'
css_path = root / 'frontend' / 'remodel.css'

html = html_path.read_text(encoding='utf-8')
css = css_path.read_text(encoding='utf-8')

link = '<link id="trekmap-remodel-css" rel="stylesheet" href="/remodel.css">'
html = re.sub(r'\s*<link id="trekmap-remodel-css"[^>]*>', '', html)
html = html.replace('</head>', link + '\n</head>', 1)

script = '''<script id="trekmap-remodel-js">\n(function(){\n  function init(){\n    const map=document.getElementById('map');\n    if(map && !document.getElementById('tm-map-hint')){\n      const hint=document.createElement('div');\n      hint.id='tm-map-hint';\n      hint.textContent='Sélectionne un trek pour afficher son parcours';\n      map.appendChild(hint);\n      setTimeout(()=>hint.classList.add('hide'),4500);\n    }\n    const sidebar=document.getElementById('sidebar');\n    if(sidebar) sidebar.setAttribute('aria-label','Exploration TrekMap France');\n    const search=document.getElementById('search');\n    if(search) search.setAttribute('aria-label','Rechercher un trek ou une région');\n    document.querySelectorAll('.map-tools button').forEach(b=>{\n      if(!b.getAttribute('title')) b.setAttribute('title',b.textContent.trim());\n    });\n  }\n  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();\n})();\n</script>'''
html = re.sub(r'\s*<script id="trekmap-remodel-js">.*?</script>', '', html, flags=re.S)
html = html.replace('</body>', script + '\n</body>', 1)
html_path.write_text(html, encoding='utf-8')
print('TrekMap UI remodel applied')
