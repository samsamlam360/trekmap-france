"""Offline protection against wrong-location and unlicensed scenic photo refs."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.smart_planner_v3 import _source_linked_scenic_photo

def photo(tags):
    return _source_linked_scenic_photo(tags)

assert photo({"wikimedia_commons":"File:Mont Aiguille panorama.jpg"}) == {
    "photo_commons_file":"Mont Aiguille panorama.jpg","photo_wikidata":""
}
assert photo({"image":"File:Belvedere.png","wikidata":"Q123456"}) == {
    "photo_commons_file":"Belvedere.png","photo_wikidata":"Q123456"
}
assert photo({"wikimedia_commons":"Category:Some landscapes"})["photo_commons_file"] == ""
assert photo({"image":"https://random.example.com/other_place.jpg"})["photo_commons_file"] == ""
assert photo({"wikimedia_commons":"File:portrait.svg"})["photo_commons_file"] == ""
assert photo({"wikimedia_commons":"File:<img src=x>.jpg"})["photo_commons_file"] == ""
assert photo({"wikimedia_commons":"File:Scene.jpg|thumb"})["photo_commons_file"] == ""
assert photo({"wikidata":"https://wikidata.org/wiki/Q123"})["photo_wikidata"] == ""
assert photo({"wikidata":"Q0"})["photo_wikidata"] == ""
assert photo({"wikidata":"Q123"})["photo_wikidata"] == "Q123"
assert photo({}) == {"photo_commons_file":"","photo_wikidata":""}
print("Scenic photos: exact OSM refs, safe Commons file, valid Wikidata ID, no generic image: PASS")
