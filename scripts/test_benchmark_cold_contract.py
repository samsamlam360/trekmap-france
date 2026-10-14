"""Offline checks for cold audit isolation, credential gating and failure exits."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import benchmark_trekbrain_v9_cold as cold
import benchmark_trekbrain_v9_render as render

assert cold.SUITE_TIMEOUT_SECONDS <= 420
assert cold.CASE_TIMEOUT_SECONDS <= 90
assert cold.MIN_INTERVAL_SECONDS >= 20

with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://do-not-use.invalid/production', 'TREKBRAIN_OSM_CACHE': '1'}):
    env = cold.isolated_environment()
    assert env['DATABASE_URL'].endswith('@127.0.0.1:1/isolated')
    assert env['TREKBRAIN_OSM_CACHE'] == '0' and env['DB_CONNECT_TIMEOUT'] == '1'
    assert os.environ['TREKBRAIN_OSM_CACHE'] == '1', 'The parent environment must remain unchanged'

assert cold.isolation_valid({'osm_cache': {'status': 'not_attempted', 'count': 0}})
for cache in [None, {}, {'count': 0}, {'status': 'hit', 'count': 1}, {'status': 'unavailable', 'count': 0}]:
    assert not cold.isolation_valid({'osm_cache': cache}), cache

# Configuration failure occurs without importing the application or external
# dependencies and preserves a report even when ORS is unavailable.
with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'ORS_API_KEY': '', 'TREKBRAIN_BENCHMARK_OUT': directory}):
    output = StringIO()
    with patch.object(cold, 'run_cases', side_effect=AssertionError('live case started without a credential')), redirect_stdout(output):
        try:
            cold.main()
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError('Missing ORS credential must have a distinct nonzero exit')
    report = json.loads((Path(directory) / 'trekbrain-cold-benchmark.json').read_text())
    assert report['configuration_errors'] == 1 and report['successful'] == 0
    assert report['rows'][0]['status'] == 'configuration_error'
    assert 'backend.app_v5' not in sys.modules

# Every geographic case gets a new child with isolated env and a finite budget.
children = []

def fake_run(command, **kwargs):
    children.append((command, kwargs))
    index = int(command[-1])
    row = {'id': cold.CASES[index][0], 'ok': False, 'structure_ok': True, 'preparation_ok': False, 'status': 'incomplete'}
    return SimpleNamespace(returncode=0, stdout=cold.PREFIX + json.dumps(row))

with patch.object(cold.subprocess, 'run', side_effect=fake_run), patch.object(cold.time, 'sleep'), redirect_stdout(StringIO()):
    rows = cold.run_cases()
assert len(children) == 4 and len(rows) == 4
for command, kwargs in children:
    assert '--case' in command and 0 < kwargs['timeout'] <= 90
    assert kwargs['env']['TREKBRAIN_OSM_CACHE'] == '0'
    assert kwargs['env']['DATABASE_URL'].endswith('@127.0.0.1:1/isolated')
assert all(row['status'] == 'incomplete' for row in rows), 'A clean child exit must not erase incomplete planning'

with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'ORS_API_KEY': 'offline-key-not-a-credential', 'TREKBRAIN_BENCHMARK_OUT': directory}):
    failed = {
        'id': 'http-refusal', 'ok': False, 'structure_ok': False,
        'preparation_ok': False, 'status': 'refused', 'hard_failures': ['HTTP 503'],
        'warnings': [], 'preparation_issues': [], 'elapsed_s': 0,
        'quality': None, 'route_distance_km': None, 'mean_daily_deviation_pct': 100,
    }
    with patch.object(cold, 'run_cases', return_value=[failed]), redirect_stdout(StringIO()):
        try:
            cold.main()
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError('Planner refusal must fail the audit, even without a crash')
    report = json.loads((Path(directory) / 'trekbrain-cold-benchmark.json').read_text())
    assert report['refused'] == 1 and report['successful'] == 0
    assert report['provider_caches_controlled'] is False

# Render build preflight may only run network-free regression scripts.
preflight = (ROOT / 'scripts/render_preflight.py').read_text()
assert 'TREKBRAIN_RUN_BENCHMARK' not in preflight
assert 'benchmark_trekbrain_v9_cold.py' not in preflight
assert 'benchmark_trekbrain_v9_render.py' not in preflight

print('Cold benchmark: fresh children, bounded budgets, cache telemetry, distinct configuration failure and refusal exit PASS')
