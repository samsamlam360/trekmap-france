"""Contrats de la navigation TrekMap en quatre espaces (sans accès réseau)."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
HIKE = (ROOT / "frontend" / "hike.html").read_text(encoding="utf-8")

for marker in ("TREKMAP_UNIFIED_EXPERIENCE_START", "TREKMAP_PROFILE_V2_START",
               "TREKMAP_INLINE_FILTERS_2026_START", "TM_HIKER_NAV_ENTRY_START",
               "TREKMAP_FOUR_SPACES_START", "TREKMAP_FOUR_SPACES_END"):
    assert HTML.count(marker) == 1, f"marqueur absent/dupliqué: {marker}"

for identifier in ("tm-primary-navigation", "tm-four-spaces-js", "tm-four-spaces-css",
                   "tm-map-filter-popover", "tm-design-add-button",
                   "tm-design-filter-button", "tm-map-options-panel",
                   "tm-mobile-nav", "tm-profile-v2", "tm-brain-route-panel"):
    assert identifier in HTML, f"fonction absente: {identifier}"

assert "['explore','⌖','Explorer']" in HTML
assert "['brain','✦','TrekBrain']" in HTML
assert "['library','▣','Mes treks']" in HTML
assert "['profile','♙','Profil']" in HTML
assert "openPrivateTab('projects')" in HTML
assert "openPrivateTab('home')" in HTML
assert "window.TrekMapProfileV2.open()" in HTML
assert "window.TrekMapOpenAI" in HTML
assert "data-filter-target" in HTML and "duration-filter" in HTML
assert "tm-mobile-create-sheet" in HTML
assert "tm-import-btn" in HTML and "tm-create-btn" in HTML
assert "TrekMapHikingNavigation" in HTML
assert "TrekBrainMapWorkspace" in HTML

for marker in ("TREKMAP_HIKE_DESIGN_START", "TREKMAP_HIKE_DESIGN_END"):
    assert HIKE.count(marker) == 1, f"mode randonnée: {marker}"
assert HIKE.count('id="quick-start"') == 1
assert HIKE.count('id="quick-tools"') == 1
assert HIKE.count('id="nav-map"') == 1
assert HIKE.count('id="hike-options"') == 1

m = re.search(r'<script id="tm-four-spaces-js">(.*?)</script>', HTML, re.S)
assert m, "le JavaScript de navigation est absent"
node = subprocess.run(["node", "--check", "--input-type=commonjs"],
                      input=m.group(1), text=True, capture_output=True)
assert node.returncode == 0, "syntaxe du JavaScript invalide: " + node.stderr

# Pas de changement de schéma/API ni de nouveaux moteurs GPS : cette couche
# reste purement navigateur et conserve les actions existantes.
installer = (ROOT / "scripts" / "apply_four_spaces_design.py").read_text(encoding="utf-8")
assert "CREATE TABLE" not in installer and "ALTER TABLE" not in installer
assert "navigator.geolocation" not in installer
assert "localStorage.setItem" not in installer
print("TrekMap four spaces: construction, syntaxe, routes utilisateur et mode randonnée OK")
