from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """User accounts: the custom user model (phone login, marketplace role, language)."""

    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"
    default_auto_field = "django.db.models.BigAutoField"
