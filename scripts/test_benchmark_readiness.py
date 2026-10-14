"""Offline benchmark gates: preserve usable routes without hiding unmet needs."""
from copy import deepcopy
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import benchmark_trekbrain_v9_production as bench

CASE = {
    'id': 'logistics-contract', 'days': 2, 'daily_km': 16,
    'expect_type': 'boucle', 'expect_close': True,
    'require_water': True, 'require_food': True,
    'require_accommodation': True, 'require_transit': False,
}


def point(day, kind, status=None):
    return {
        'kind': kind, 'route_day': day, 'status': status,
        'lat': 48.0, 'lon': 1.0,
        'source_url': f'https://www.openstreetmap.org/node/{day + (100 if kind == "food" else 0)}',
    }


def sample():
    return {
        'route_type': 'Boucle', 'start': {'lat': 48.0, 'lon': 1.0},
        'end': {'lat': 48.0, 'lon': 1.0},
        'route_preview': {
            'coords': [[48.0, 1.0], [48.01, 1.03], [48.0, 1.0]],
            'fallback': False, 'distance_km': 32.0,
        },
        'stages': [{'day': 1, 'distance_km': 16}, {'day': 2, 'distance_km': 16}],
        'trekbrain': {'quality': {'score': 95, 'blockers': []}},
        'map_resources': {'points': [point(day, kind, 'potable_referenced' if kind == 'water' else None) for day in (1, 2) for kind in ('water', 'food')]},
        'logistics': {'nights': [{'night': 1, 'status': 'confirmed', 'access_mode': 'walk'}]},
    }


def evaluate(payload, case=CASE):
    return bench.evaluate(case, payload, 3.0, {})


ready = evaluate(sample())
assert ready['ok'] and ready['structure_ok'] and ready['preparation_ok'], ready
assert ready['status'] == 'ready', ready

partial = sample()
partial['map_resources']['points'] = [point(1, 'water', 'unverified'), point(1, 'food')]
partial['logistics']['nights'] = [{'night': 1, 'status': 'usable_with_transfer', 'access_mode': 'transfer'}]
partial['stages'][1]['water_notes'] = 'Prévoir une réserve et vérifier les sources'
row = evaluate(partial)
assert row['structure_ok'] and not row['preparation_ok'] and not row['ok'], row
assert row['status'] == 'incomplete', row
issues = {item['code']: item for item in row['preparation_issues']}
assert issues['water_missing']['days'] == [1, 2], issues
assert issues['food_missing']['days'] == [2], issues
assert issues['accommodation_missing']['days'] == [1], issues

transfer = sample()
transfer['logistics']['nights'] = [{'night': 1, 'status': 'usable_with_transfer', 'transfer_confirmed': True}]
assert evaluate(transfer)['ok']

# Evidence can exceed the display limit; all route-local evidence matters.
limited = sample()
limited['map_resources']['evidence_points'] = deepcopy(limited['map_resources']['points'])
limited['map_resources']['points'] = []
assert evaluate(limited)['ok']

fake_source = sample()
fake_source['map_resources']['points'][0]['source_url'] = 'https://www.openstreetmap.org.evil.example/node/1'
assert not evaluate(fake_source)['preparation_ok']

nonpotable = sample()
nonpotable['map_resources']['points'][0]['status'] = 'not_potable'
assert not evaluate(nonpotable)['ok']

optional = dict(CASE, require_water=False, require_food=False, require_accommodation=False)
assert evaluate(partial, optional)['ok']

blocked = sample()
blocked['trekbrain']['quality']['blockers'] = ['objectif incontournable non satisfait']
row = evaluate(blocked)
assert row['structure_ok'] and not row['preparation_ok'] and row['status'] == 'incomplete', row

published = sample()
published['trip_readiness'] = {
    'version': 1, 'status': 'incomplete', 'label': 'Préparation incomplète',
    'requirements': {'water': {'required': True, 'status': 'missing', 'missing_days': [2], 'detail': 'Eau manquante J2'}},
    'issues': [{'code': 'water_missing', 'requirement': 'water', 'days': [2], 'detail': 'Eau manquante J2'}],
}
assert evaluate(published)['status'] == 'incomplete'
published['trip_readiness']['status'] = 'ready'
published['trip_readiness']['issues'] = []
assert not evaluate(published)['ok'], 'A ready verdict cannot contradict mandatory requirement telemetry'

for distance in [float('nan'), float('inf'), True, 'unavailable']:
    broken = sample()
    broken['stages'][0]['distance_km'] = distance
    row = evaluate(broken)
    assert not row['structure_ok'] and row['status'] == 'refused', (distance, row)

with tempfile.TemporaryDirectory() as directory:
    bench.OUT_DIR = Path(directory)
    bench.write_reports({'error': 'configuration_error'}, [])
    assert 'configuration_error' in (bench.OUT_DIR / 'trekbrain-production-benchmark.md').read_text()
    bench.write_reports({}, [ready, evaluate(partial), bench.failure_row('declined', 'HTTP 503')])
    report = (bench.OUT_DIR / 'trekbrain-production-benchmark.md').read_text()
    assert 'structurellement valides: **2/3**' in report, report
    assert 'préparation complète: **1/3**' in report, report
    assert '| incomplete |' in report and '| refused |' in report, report

print('Benchmark preparation: route validity, requested daily evidence, transfers, goals and categorized reports PASS')
