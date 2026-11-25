"""ASGI entry point. Defaults to production settings.

The MVP uses polling (no WebSockets); WSGI is the primary deployment target.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
