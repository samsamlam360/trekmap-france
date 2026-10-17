"""Contrat de la refonte de fiche et de bibliothèque TrekMap."""
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
html=(root/'frontend/index.html').read_text(encoding='utf-8')
for key in ['TM_DETAIL_PROFILE_POLISH_START','TM_DETAIL_PROFILE_POLISH_END']:
    assert html.count(key)==1, f'Marqueur manquant ou répété: {key}'
for key in ['tm-detail-refined','tm-detail-overview','tm-detail-secondary',
            'tm-detail-secondary-buttons','tm-p-status-filter','tm-p-status-search',
            'tm-p-status-empty','tm-p-more','tm-p-collection-tools',
            'TrekMapDetailProfilePolish']:
    assert key in html, f'Composant manquant: {key}'
for key in ['fav-detail','export-detail','hike-navigate-detail','plan-detail',
            'edit-detail','delete-detail','tm-advanced-edit',
            'tm-p-journey-form','tm-p-journey-card','tm-p-collection-content',
            'tm-p-checkline','tm-p-plan-editor','tm-p-exit']:
    assert key in html, f'Ancien contrôle cassé: {key}'
script=re.search(r'<script id="tm-detail-profile-polish-js">([\s\S]*?)</script>',html)
assert script,'Script de refonte absent'
p=subprocess.run(['node','--check','--input-type=commonjs'],
                 input=script.group(1),text=True,capture_output=True)
assert p.returncode==0,p.stderr
installer=(root/'scripts/apply_detail_profile_polish.py').read_text(encoding='utf-8')
assert 'CREATE TABLE' not in installer and 'ALTER TABLE' not in installer
assert 'navigator.geolocation' not in installer and 'localStorage.setItem' not in installer
print('TrekMap détail / profil: intégration, sécurité des handlers et syntaxe validées')
