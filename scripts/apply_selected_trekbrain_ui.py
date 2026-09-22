"""Apply only the UI matching the explicitly selected TrekBrain runtime."""
from __future__ import annotations

import os
import runpy
from pathlib import Path


version = os.getenv("TREKBRAIN_VERSION", "v8").strip().casefold()
if version == "v9":
    base = Path(__file__)
    runpy.run_path(str(base.with_name("apply_trekbrain_v9_ui.py")), run_name="__main__")
    runpy.run_path(str(base.with_name("apply_trekbrain_v9_map_ui.py")), run_name="__main__")
    runpy.run_path(str(base.with_name("apply_trekbrain_error_guard.py")), run_name="__main__")
    runpy.run_path(str(base.with_name("apply_trekbrain_failure_actions.py")), run_name="__main__")
    runpy.run_path(str(base.with_name("apply_trekbrain_diagnostics_ui.py")), run_name="__main__")
elif version != "v8":
    raise SystemExit("TREKBRAIN_VERSION doit valoir v8 ou v9.")
else:
    print("TrekBrain v8 UI conservée.")
