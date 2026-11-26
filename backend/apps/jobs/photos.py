"""Optional job photos (JOB-04): JPEG / PNG / WebP, ≤ 5 MB, at most five per request.

The server checks the actual content (magic bytes, Pillow decode, format match, pixel limit) and
then RE-ENCODES the image without metadata, which removes EXIF data including GPS location. EXIF
orientation is applied first so the photo still appears the right way up. Files are stored
privately with random names; downloads are authorised per request owner in the view. Photos are
reference material only: they are never sent to AI interpretation (no visual diagnosis).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from rest_framework import status

from apps.core.api.exceptions import ApiError

MAX_PHOTOS = 5
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
MIN_SIDE = 50
TYPES = {
    "image/jpeg": (lambda b: b[:3] == b"\xff\xd8\xff", "JPEG"),
    "image/png": (lambda b: b[:8] == b"\x89PNG\r\n\x1a\n", "PNG"),
    "image/webp": (lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP", "WEBP"),
}


class PhotoTooLarge(ApiError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "image_too_large"
    default_detail = "The photo is too large. Please use a photo under 5 MB."


class PhotoUnsupported(ApiError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_code = "image_unsupported"
    default_detail = "Please use a JPEG, PNG or WebP photo."


class PhotoDimensions(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "image_dimensions"
    default_detail = "The photo is too small or too large."


class TooManyPhotos(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "too_many_photos"
    default_detail = "A request can have at most five photos."


@dataclass(frozen=True)
class CleanPhoto:
    data: bytes
    mime_type: str
    width: int
    height: int
    sha256: str


def clean_photo(data: bytes) -> CleanPhoto:
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > MAX_BYTES:
        raise PhotoTooLarge(details={"max_bytes": MAX_BYTES})
    mime_type = next((kind for kind, (matches, _) in TYPES.items() if matches(data)), None)
    if mime_type is None:
        raise PhotoUnsupported()
    pil_format = TYPES[mime_type][1]
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != pil_format:
                raise PhotoUnsupported()
            if probe.width * probe.height > MAX_PIXELS:
                raise PhotoDimensions(details={"reason": "too_large"})
            probe.verify()
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened)  # keep orientation, then drop all metadata
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise PhotoUnsupported() from None
    if min(image.size) < MIN_SIDE:
        raise PhotoDimensions(details={"reason": "too_small"})

    if pil_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = io.BytesIO()
    options = {"JPEG": {"quality": 90, "optimize": True}, "PNG": {"optimize": True}, "WEBP": {"quality": 90}}[pil_format]
    image.save(buffer, format=pil_format, **options)  # no exif=/pnginfo= → metadata is not written
    clean = buffer.getvalue()
    return CleanPhoto(clean, mime_type, image.width, image.height, hashlib.sha256(clean).hexdigest())
