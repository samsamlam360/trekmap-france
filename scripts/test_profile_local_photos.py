"""Validation locale des photos. Aucun acces Neon ni appel reseau."""
import base64

from fastapi import HTTPException
from backend.profile_v2 import _photo_url

def data_url(raw, mime="jpeg"):
    return "data:image/" + mime + ";base64," + base64.b64encode(raw).decode("ascii")

jpeg = b"\xff\xd8\xff" + b"\x00" * 5000 + b"\xff\xd9"
assert _photo_url(data_url(jpeg)) == data_url(jpeg)
webp = b"RIFF" + b"\x04\x00\x00\x00" + b"WEBP" + b"VP8 "
assert _photo_url(data_url(webp, "webp")) == data_url(webp, "webp")
assert _photo_url("https://example.org/picture.jpg") == "https://example.org/picture.jpg"

for invalid in (
    data_url(b"<svg />", "svg+xml"),
    data_url(b"not-a-jpeg"),
    data_url(jpeg, "webp"),
    data_url(jpeg + b"x" * (121 * 1024)),
    "data:text/html;base64,PHNjcmlwdD4=",
    "http://example.org/picture.jpg",
    "https://evil:password@example.org/image.jpg",
):
    try:
        _photo_url(invalid)
    except HTTPException as err:
        assert err.status_code == 422, (invalid[:40], err)
    else:
        raise AssertionError("Unsafe image accepted: " + invalid[:40])

print("PROFILE LOCAL PHOTO PASS: JPG/WebP, size bounds, invalid URLs and SVG blocked")
