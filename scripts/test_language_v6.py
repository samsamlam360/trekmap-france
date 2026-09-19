"""Offline regression tests for TrekMap French understanding v6."""
from backend import smart_planner_v6  # noqa: F401 - loads the v6 language pack
from backend.compound_language_v5 import extract_side_requests
from backend.language_engine import normalize_for_planner

raw = (
    "Je voudrai 4 jours pepere dans le Vercors avec 15 bornes par jour, "
    "je voudrai visite un chato le 2e jour et qu'on passe par un villlage "
    "avec une festivale le 14 julliet si possible, sans bagnole et avec de beaux spots."
)
normalized, matches = normalize_for_planner(raw)
compound = extract_side_requests(normalized)
requests = compound["side_requests"]

assert "15 km" in normalized, normalized
assert "chateau" in normalized, normalized
assert "village" in normalized, normalized
assert "festival" in normalized or "evenement" in normalized, normalized
assert "juillet" in normalized, normalized
assert "train" in normalized and "panorama" in normalized, normalized

kinds = {item["kind"] for item in requests}
for expected in {"castle", "village", "event"}:
    assert expected in kinds, (expected, requests, normalized)

castle = next(item for item in requests if item["kind"] == "castle")
assert castle["preferred_day"] == 2, castle

event = next(item for item in requests if item["kind"] == "event")
assert event["target_date"] and event["target_date"].endswith("-07-14"), event
assert event["required"] is False, event  # "si possible" must remain a preference.

print("TrekMap v6 French long-request parser: OK")
print(normalized)
print(requests)
