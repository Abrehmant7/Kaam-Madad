"""Root URL configuration.

/api/v1/...   JSON API (Django REST Framework)
/admin/...    Django Admin for staff workflows
/static/...   Collected static files (served by WhiteNoise)
everything else → the React single-page app (index.html from the Vite build)
"""

from django.contrib import admin
from django.urls import include, path, re_path

from apps.core.config_view import ClientConfigView
from apps.invitations import urls as invitation_urls
from apps.voice import urls as voice_urls
from apps.workers import urls as worker_urls
from apps.core.views import api_not_found, spa_index

admin.site.site_header = "Kaam Madad staff administration"
admin.site.site_title = "Kaam Madad admin"
admin.site.index_title = "Staff workflows"

api_v1_patterns = [
    path("health/", include("apps.core.urls")),
    path("config/", ClientConfigView.as_view(), name="client-config"),
    path("auth/", include("apps.accounts.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("audio/", include(voice_urls.audio_patterns)),
    path("interpretations/", include(voice_urls.interpretation_patterns)),
    path("instructions/", include(voice_urls.instruction_patterns)),
    path("workers/", include(worker_urls.worker_patterns)),
    path("identity/", include(worker_urls.identity_patterns)),
    path("jobs/", include("apps.jobs.urls")),
    path("jobs/", include(invitation_urls.customer_patterns)),
    path("invitations/", include(invitation_urls.worker_patterns)),
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
