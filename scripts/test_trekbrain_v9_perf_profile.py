"""Regression tests for request-local TrekBrain v9 performance profiling."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import trekbrain_perf_profile_v9 as perf


token = perf.begin({"days": 3, "route_type": "boucle"})
profile = perf.current()
assert profile is not None

seq1 = perf.next_sequence("ors.directions")
seq2 = perf.next_sequence("ors.directions")
assert (seq1, seq2) == (1, 2)

perf.record("ors.directions", 12.4, attempt=seq1, outcome="ok")
perf.record("ors.matrix", 0.0, cache_hit=True, outcome="cache")

with ThreadPoolExecutor(max_workers=1) as pool:
    pool.submit(
        perf.record,
        "photon.lookup",
        8.5,
        profile=profile,
        outcome="ok",
    ).result()

result = {"planner": {}, "agent": {"performance": {}}}
summary = perf.finish(token, result)
assert summary is not None
assert summary["providers"]["ors.directions"]["count"] == 1
assert summary["providers"]["ors.matrix"]["cache_hits"] == 1
assert summary["providers"]["photon.lookup"]["count"] == 1
assert result["planner"]["performance_profile"]["version"] == 1
assert result["agent"]["performance"]["provider_profile"]["ors.directions"]["total_ms"] == 12
assert perf.current() is None

print("TrekBrain v9 performance profiler: OK")
