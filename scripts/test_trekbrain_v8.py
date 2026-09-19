"""Offline regression tests for TrekBrain v8 learning and strategy selection."""
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.trekbrain_v8 import (  # noqa: E402
    _state_template,
    extract_features,
    learn_state,
    rank_actions,
    raw_score,
)


def req(prompt, *, days=3, km=18, difficulty="medium", route="Boucle", transit=False, water=False, sleep=False, food=False):
    return SimpleNamespace(
        prompt=prompt,
        days=days,
        daily_km=km,
        difficulty=difficulty,
        route_type=route,
        require_transit=transit,
        require_water=water,
        require_accommodation=sleep,
        require_food=food,
    )


scenic_data = req("Je veux surtout des lacs, de beaux paysages et des panoramas")
scenic_features = extract_features(scenic_data, scenic_data.prompt, {"side_requests": [], "dates": {}})
scenic_rank = rank_actions(_state_template(), scenic_features)
assert scenic_rank[0]["action"] == "scenic", scenic_rank[:3]

log_data = req("Sans voiture, camping chaque soir et ravitaillement facile", transit=True, sleep=True, food=True)
log_features = extract_features(log_data, log_data.prompt, {"side_requests": [], "dates": {}})
log_rank = rank_actions(_state_template(), log_features)
assert log_rank[0]["action"] == "logistics", log_rank[:3]

heritage_compound = {
    "side_requests": [
        {"kind": "event", "target_date": "2027-07-14"},
        {"kind": "castle", "target_date": None},
    ],
    "dates": {"start_date": "2027-07-12"},
}
event_data = req("Passer par un château puis une fête de village le 14 juillet")
event_features = extract_features(event_data, event_data.prompt, heritage_compound)
event_rank = rank_actions(_state_template(), event_features)
assert event_rank[0]["action"] in {"events", "heritage"}, event_rank[:3]

state = _state_template()
before = raw_score(state, "scenic", scenic_features)
for _ in range(6):
    state = learn_state(state, "scenic", scenic_features, 1.0)
after_positive = raw_score(state, "scenic", scenic_features)
assert after_positive > before, (before, after_positive)

for _ in range(12):
    state = learn_state(state, "scenic", scenic_features, -1.0)
after_negative = raw_score(state, "scenic", scenic_features)
assert after_negative < after_positive, (after_positive, after_negative)
assert state["samples"] == 18, state["samples"]

print("TrekBrain v8 strategy selection + online learning: OK")
print("scenic before/positive/negative:", round(before, 3), round(after_positive, 3), round(after_negative, 3))
