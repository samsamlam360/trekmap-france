"""Fast application boot invariants, including syntax of composed scripts."""
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
html=(root/"frontend"/"index.html").read_text(encoding="utf-8")
src=(root/"scripts"/"apply_unified_experience.py").read_text(encoding="utf-8")
api=(root/"backend"/"fast_catalog.py").read_text(encoding="utf-8")
switch=(root/"backend"/"account_switch.py").read_text(encoding="utf-8")
for identifier in ("TM_FAST_ACCOUNTS_START","TM_FAST_ACCOUNTS_END",
                   "tm-fast-accounts-js","tm-accounts-list",
                   "tm-switch-accounts","TrekMapAccounts"):
    assert html.count(identifier)>=1,identifier
assert "/catalog/bootstrap" in html
assert "Promise" in html and "treks/geojson" in html
assert "cachedTraceLayers" in html and ".setStyle(" in html
assert "await restoreSession();await loadTraces();" in html
assert "document.dispatchEvent(new Event('trekmap:catalog-ready'))" in html
assert "fetch(api()+'/treks',{cache:'no-store'})" not in src
assert "allTreksSafe()" in src
assert "GZipMiddleware" in api
assert "WHERE t.is_public=TRUE OR t.owner_id=:uid OR :admin=TRUE" in api
assert "HttpOnly" in switch and "user_account_devices" in switch
assert "secrets.token_urlsafe(48)" in switch
assert "DELETE FROM user_sessions" in switch
for tag in ("tm-fast-accounts-js",):
    js=re.search(r'<script id="'+re.escape(tag)+r'">([\s\S]*?)</script>',html)
    assert js,tag
    r=subprocess.run(["node","--check","--input-type=commonjs"],
                     input=js.group(1),text=True,capture_output=True)
    assert r.returncode==0,r.stderr
print("FAST BOOT STATIC PASS: no redundant full treks fetch, progressive map, safe account UI")
