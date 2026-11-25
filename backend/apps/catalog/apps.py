from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Database-backed service catalog: trades, service tags, cities/areas, speciality questions."""

    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Service catalog"
    default_auto_field = "django.db.models.BigAutoField"
