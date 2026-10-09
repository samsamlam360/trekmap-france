"""Live first-visit audit: fresh process, no database, no saved model or POIs.

Run only in the opt-in Render benchmark environment. Each child inherits the
existing free routing credentials, but cannot connect to Neon or save data.
Provider-side caches are outside TrekBrain's control and are not claimed cold.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("huelgoat", "Huelgoat, Finistère", 2, 16),
    ("bagnoles", "Bagnoles-de-l'Orne, Orne", 2, 16),
    ("gerardmer", "Gérardmer, Vosges", 2, 16),
    ("saint-antonin", "Saint-Antonin-Noble-Val, Tarn-et-Garonne", 2, 16),
]
PREFIX = "[TrekBrain cold] "

def isolated_environment():
    env = dict(os.environ)
    env.update(DATABASE_URL="postgresql://benchmark:benchmark@127.0.0.1:1/isolated",
               DB_CONNECT_TIMEOUT="1", TREKBRAIN_OSM_CACHE="0",
               TREKBRAIN_FREE_MODE="1", TREKMAP_ENV="development",
               PYTHONUNBUFFERED="1")
    return env

def child(index):
    # Set isolation even for direct child invocation, before importing the app.
    os.environ.update(isolated_environment())
    sys.path.insert(0, str(ROOT))
    from benchmark_trekbrain_v9_render import _plan_endpoint, _summary
    from backend.free_planner_v2 import AIPlanRequest
    from fastapi import HTTPException
    name, region, days, daily = CASES[index]
    request = AIPlanRequest(
        prompt=f"Boucle à pied de {days} jours autour de {region}, environ {daily} km par jour, avec gîte, eau et ravitaillement.",
        region=region, days=days, daily_km=daily, route_type="Boucle",
        require_transit=False, require_food=True, require_water=True,
        require_accommodation=True,
    )
    started = time.perf_counter()
    try:
        result = _plan_endpoint()(request, {"id": 0, "username": "cold-audit", "is_admin": False})
        row = _summary(name, result, time.perf_counter()-started)
        row["quality_acceptable"] = not bool(row.get("blockers"))
        row["nights"] = (result.get("logistics") or {}).get("nights") or []
        row["coverage"] = (result.get("map_resources") or {}).get("coverage") or {}
        row["osm_cache"] = ((result.get("planner") or {}).get("resource_overlay") or {}).get("osm_cache") or {}
        row["cache_isolation_valid"] = int(row["osm_cache"].get("count") or 0) == 0
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        row = {"case": name, "ok": False, "http_status": exc.status_code,
               "error": str(detail.get("message") or detail.get("detail") or "")[:500],
               "diagnostic": detail.get("diagnostic"), "elapsed_s": round(time.perf_counter()-started, 2)}
    row.update(isolated_process=True, persistent_cache_disabled=True, database_isolated=True)
    print(PREFIX+json.dumps(row, ensure_ascii=False), flush=True)

def main():
    rows = []
    last_started = None
    for index, case in enumerate(CASES):
        if last_started is not None:
            time.sleep(max(0.0, 20.0 - (time.monotonic() - last_started)))
        last_started = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--case", str(index)],
                env=isolated_environment(), cwd=ROOT, capture_output=True, text=True, timeout=90)
            records = [line[len(PREFIX):] for line in proc.stdout.splitlines() if line.startswith(PREFIX)]
            if proc.returncode or len(records) != 1:
                row = {"case": case[0], "ok": False, "error": "child_failed", "returncode": proc.returncode}
            else:
                row = json.loads(records[0])
        except subprocess.TimeoutExpired:
            row = {"case": case[0], "ok": False, "error": "timeout_90s"}
        rows.append(row)
        print(PREFIX+json.dumps(row, ensure_ascii=False), flush=True)
    print("[TrekBrain cold summary] "+json.dumps({"cases":len(rows),
          "successful":sum(bool(r.get('ok')) for r in rows), "rows":rows}, ensure_ascii=False), flush=True)
    # A provider/constraint refusal is reported, never relabelled successful.
    # Runtime crashes or a broken isolation contract are deployment blockers.
    if any(r.get("error") in {"child_failed", "timeout_90s"}
           or r.get("cache_isolation_valid") is False for r in rows):
        raise SystemExit("Cold audit crashed or isolation failed")

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--case":
        child(int(sys.argv[2]))
    else:
        main()
