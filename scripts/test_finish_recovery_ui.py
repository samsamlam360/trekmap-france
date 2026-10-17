"""Tests structurels de la bibliothèque, du login et de l'UX finale."""
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
page=(root/'frontend/index.html').read_text(encoding='utf-8')
profile=(root/'scripts/apply_profile_v2.py').read_text(encoding='utf-8')
api=(root/'backend/password_reset.py').read_text(encoding='utf-8')
assert page.count('TM_FINISH_RECOVERY_START')==1
assert page.count('TM_FINISH_RECOVERY_END')==1
for item in ('tm-forgot-link','tm-forgot-email','tm-new-reset-password',
             'tm-confirm-reset-password','TrekMapRecoveryUI',
             'tm-p-status-filter','tm-library-categories','data-tm-origin',
             'tm-ai-overlay','tm-brain-route-panel'):
    assert item in page, item
for key in ('data-p-origin','ownedIds','favoriteIds','accountTreks()'):
    assert key in profile, key
assert 'password_reset_tokens' in api and 'consumed_at' in api
assert 'hashlib.sha256' in api and 'secrets.token_urlsafe(48)' in api
assert 'DELETE FROM user_sessions' in api
assert 'RESEND_API_KEY' in api and 'RESET_EMAIL_FROM' in api
assert 'GET /auth' not in api
js=re.search(r'<script id="tm-finish-recovery-js">([\s\S]*?)</script>',page)
assert js,"UI JS missing"
r=subprocess.run(['node','--check','--input-type=commonjs'],
                 input=js.group(1),capture_output=True,text=True)
assert r.returncode==0,r.stderr
assert 'TM_DETAIL_PROFILE_POLISH_START' in page
assert 'tm-p-journey-form' in page
assert 'tm-p-collection-content' in page
print('UX finale OK: création/favoris séparés, récupération du compte et TrekBrain')
