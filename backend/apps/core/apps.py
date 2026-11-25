from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Cross-cutting foundation: request IDs, API errors, health checks, SPA serving."""

    name = "apps.core"
    label = "core"
    verbose_name = "Core"
