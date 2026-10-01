"""Add a small, isolated readability layer to the TrekBrain planner modal.

This script intentionally does not touch TrekBrain planning logic or JavaScript.
It only makes the two modal columns scroll independently and keeps a visible
scrollbar, so long plans remain readable on desktop and mobile.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
html_path = root / "frontend" / "index.html"
html = html_path.read_text(encoding="utf-8")

html = re.sub(
    r"\s*<!-- TREKMAP_TREKBRAIN_SCROLL_UI_START -->.*?<!-- TREKMAP_TREKBRAIN_SCROLL_UI_END -->\s*",
    "\n",
    html,
    flags=re.S,
)

if "TREKMAP_AI_EXPERIENCE_START" not in html:
    raise SystemExit("L'interface TrekBrain doit être construite avant la couche de défilement.")

block = r'''<!-- TREKMAP_TREKBRAIN_SCROLL_UI_START -->
<style id="trekmap-trekbrain-scroll-css">
/* Long TrekBrain results must scroll inside the modal instead of being clipped. */
#tm-ai-overlay .tm-ai-shell{
  min-height:0;
}
#tm-ai-overlay .tm-ai-side,
#tm-ai-overlay .tm-ai-result{
  min-height:0;
  overflow-y:auto!important;
  overflow-x:hidden!important;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
  scrollbar-width:auto;
  scrollbar-color:#829b8f #edf3ef;
}
#tm-ai-overlay .tm-ai-side::-webkit-scrollbar,
#tm-ai-overlay .tm-ai-result::-webkit-scrollbar{
  width:12px;
}
#tm-ai-overlay .tm-ai-side::-webkit-scrollbar-track,
#tm-ai-overlay .tm-ai-result::-webkit-scrollbar-track{
  background:#edf3ef;
  border-radius:999px;
}
#tm-ai-overlay .tm-ai-side::-webkit-scrollbar-thumb,
#tm-ai-overlay .tm-ai-result::-webkit-scrollbar-thumb{
  min-height:54px;
  background:#829b8f;
  border:3px solid #edf3ef;
  border-radius:999px;
}
#tm-ai-overlay .tm-ai-side::-webkit-scrollbar-thumb:hover,
#tm-ai-overlay .tm-ai-result::-webkit-scrollbar-thumb:hover{
  background:#627d70;
}

/* Slightly more breathing room in long generated plans. */
#tm-ai-overlay .tm-ai-result .tm-ai-section{margin-top:20px}
#tm-ai-overlay .tm-ai-result .tm-ai-stage{padding:14px 15px;margin-bottom:11px}
#tm-ai-overlay .tm-ai-result .tm-ai-stage-head b{font-size:14px;line-height:1.4}
#tm-ai-overlay .tm-ai-result .tm-ai-stage-head span{font-size:12px}
#tm-ai-overlay .tm-ai-result #tm-ai-content{padding-bottom:28px}

@media(min-width:821px){
  #tm-ai-overlay .tm-ai-shell{
    width:min(1320px,calc(100vw - 36px));
    height:min(92dvh,900px);
    max-height:calc(100dvh - 36px);
  }
}

@media(max-width:820px){
  #tm-ai-overlay .tm-ai-side,
  #tm-ai-overlay .tm-ai-result{
    scrollbar-width:thin;
  }
  #tm-ai-overlay .tm-ai-side::-webkit-scrollbar,
  #tm-ai-overlay .tm-ai-result::-webkit-scrollbar{
    width:8px;
  }
}
</style>
<!-- TREKMAP_TREKBRAIN_SCROLL_UI_END -->'''

html = html.replace("</body>", block + "\n</body>", 1)
html_path.write_text(html, encoding="utf-8")
print("TrekBrain scroll/readability UI applied")
