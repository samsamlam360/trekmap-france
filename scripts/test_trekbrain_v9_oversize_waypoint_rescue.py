"""The active fast recovery must reach routed waypoint fallback after Matrix fails."""
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import trekbrain_roundtrip_v9 as rt

v3=SimpleNamespace(_route_retrace_ratio=lambda coords: .1)
start={'lat':45,'lon':5}
oversized={'coords':[[45,5],[45.1,5.1],[45.2,5],[45,5]], 'distance':39.8,
           'fallback':False, 'routing_mode':'ors-round-trip'}
feasible={**oversized,'distance':26.,'routing_mode':'ors-waypoint-loop'}
old=(rt._roundtrip_request,rt._matrix_subloop_candidates,rt._polygon_loop_candidates)
calls=[]
try:
    rt._roundtrip_request=lambda *a:(dict(oversized),None)
    rt._matrix_subloop_candidates=lambda *a:[]
    def waypoint(*args):
        calls.append(args)
        return [dict(feasible)]
    rt._polygon_loop_candidates=waypoint
    result=rt._recover_unranked_oversized_roundtrip(dict(oversized),start,26.,9.75,16.25,2,v3)
    assert result['distance']==26. and result['distance_window_preferred'],result
    assert len(calls)==1 and result['routing_mode']=='ors-waypoint-loop'
    # Already usable routes incur no extra network fallback.
    calls.clear()
    ready={**oversized,'distance':26.}
    assert rt._recover_unranked_oversized_roundtrip(ready,start,26.,9.75,16.25,2,v3) is ready
    assert not calls
    # An oversized waypoint route must not bypass the existing distance gate.
    rt._polygon_loop_candidates=lambda *a:[{**feasible,'distance':38.}]
    result=rt._recover_unranked_oversized_roundtrip(dict(oversized),start,26.,9.75,16.25,2,v3)
    assert not result['distance_window_preferred']
finally:
    rt._roundtrip_request,rt._matrix_subloop_candidates,rt._polygon_loop_candidates=old
print('Oversized fast recovery: routed waypoint candidate considered; no extra successful-path calls; ceiling preserved: PASS')
