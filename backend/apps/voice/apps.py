from django.apps import AppConfig


class VoiceConfig(AppConfig):
    """Private audio, transcription, interpretation drafts and speech synthesis (M3)."""

    name = "apps.voice"
    label = "voice"
    verbose_name = "Voice and AI drafts"
    default_auto_field = "django.db.models.BigAutoField"
