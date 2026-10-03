"""Offline regression tests for TrekMap French understanding v6."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

# Route anchors are not side objectives. The Morvan production prompt used to
# mark "lac des Settons" as a mandatory secondary objective simply because the
# clause also contained "Je veux une boucle", capping an otherwise valid route
# at 59/100.
anchor_text, _ = normalize_for_planner(
    "Je veux une boucle tranquille de 3 jours dans le Morvan autour du lac des Settons, "
    "environ 16 km par jour, avec camping, eau et ravitaillement."
)
anchor_requests = extract_side_requests(anchor_text)["side_requests"]
assert not any(item["kind"] == "lake" for item in anchor_requests), anchor_requests

# Genuine side preferences must still be extracted.
preference_text, _ = normalize_for_planner(
    "Je veux une randonnée avec un beau lac et un village typique."
)
preference_kinds = {item["kind"] for item in extract_side_requests(preference_text)["side_requests"]}
assert {"lake", "village"} <= preference_kinds, preference_kinds

print("TrekMap v6 French long-request parser: OK")
print(normalized)
print(requests)
