"""GET /api/v1/config/ — public, non-secret client configuration.

Lets the UI show a persistent demo label and an honest phone-confirmation state.
Values come only from server settings; the client cannot change them.
"""

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@method_decorator(never_cache, name="dispatch")
class ClientConfigView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.accounts.phone_verification import provider_status
        from apps.providers import registry
        from apps.workers.identity import provider_status as identity_status

        return Response(
            {
                "deployment_mode": settings.DEPLOYMENT_MODE,
                "phone_verification": provider_status(),
                "ai": registry.status(),
                "identity_verification": identity_status(),
                "voice_limits": {
                    "max_audio_bytes": settings.VOICE_LIMITS["MAX_AUDIO_BYTES"],
                    "max_audio_seconds": settings.VOICE_LIMITS["MAX_AUDIO_SECONDS"],
                    "max_synthesis_chars": settings.VOICE_LIMITS["MAX_SYNTHESIS_CHARS"],
                },
                "languages": [code for code, _name in settings.LANGUAGES],
                "default_language": "ur",
            }
        )
