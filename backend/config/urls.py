"""Root URL configuration.

/api/v1/...   JSON API (Django REST Framework)
/admin/...    Django Admin for staff workflows
/static/...   Collected static files (served by WhiteNoise)
everything else → the React single-page app (index.html from the Vite build)
"""

from django.contrib import admin
from django.urls import include, path, re_path

from apps.core.views import api_not_found, spa_index

admin.site.site_header = "Kaam Madad staff administration"
admin.site.site_title = "Kaam Madad admin"
admin.site.index_title = "Staff workflows"

api_v1_patterns = [
    path("health/", include("apps.core.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1_patterns)),
    # Any other /api/ path returns a structured JSON 404, never the SPA.
    re_path(r"^api/", api_not_found),
    path("admin/", admin.site.urls),
    # Client-side routes. Excludes API, admin and static prefixes.
    re_path(r"^(?!api/|admin/|static/).*$", spa_index, name="spa"),
]

# API-aware error handlers: JSON envelope under /api/, Django defaults elsewhere.
handler400 = "apps.core.views.handler400"
handler403 = "apps.core.views.handler403"
handler404 = "apps.core.views.handler404"
handler500 = "apps.core.views.handler500"
