"""Cache policy for static assets served by WhiteNoise.

Kept free of Django imports because settings reference it directly.
Only content-hashed files may be cached "forever"; everything else (including
index.html) must be revalidated so a new deployment is picked up immediately.
"""

from __future__ import annotations

import re

# Vite build output, e.g. /assets/index-BxYz12_3.js (8-character content hash).
_VITE_HASHED_ASSET = re.compile(r"^/assets/.+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
# Django ManifestStaticFilesStorage output, e.g. /static/admin/css/base.5af66c1b1797.css
_DJANGO_HASHED_STATIC = re.compile(r"^/static/.+\.[0-9a-f]{12}\.[A-Za-z0-9]+$")


def is_immutable_asset(path: str, url: str) -> bool:
    return bool(_VITE_HASHED_ASSET.match(url) or _DJANGO_HASHED_STATIC.match(url))
