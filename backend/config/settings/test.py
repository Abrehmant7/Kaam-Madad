"""Settings for the automated test suite (runs against a real PostgreSQL test database).

Usage: python manage.py test --settings=config.settings.test
"""

from .development import *  # noqa: F403

# Fast hashing keeps tests quick. Never use this hasher outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep test output readable; warnings and errors still surface.
LOGGING["loggers"]["apps"]["level"] = "ERROR"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "ERROR"  # noqa: F405

# Tests never call real providers or use real credentials, whatever the developer's .env contains:
# simulated (fixture) providers in a demo deployment, and every provider key blanked.
DEPLOYMENT_MODE = "demo"
PHONE_VERIFICATION_PROVIDER = "demo"
SPEECH_TO_TEXT_PROVIDER = "fixture"
INTERPRETATION_PROVIDER = "fixture"
TEXT_TO_SPEECH_PROVIDER = "fixture"
CNIC_OCR_PROVIDER = "tesseract"  # a local program, no credentials; API tests replace it with a stub
IDENTITY_VERIFICATION_PROVIDER = "demo_registry"
GEMINI_API_KEY = ""
AZURE_SPEECH_KEY = ""
AZURE_SPEECH_REGION = ""
ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_ID = ""
GEMINI_STT_MODEL = "gemini-3.8-flash"
GEMINI_INTERPRETATION_MODEL = "gemini-3.8-flash"
ELEVENLABS_MODEL_ID = "eleven_v3"
ELEVENLABS_API_BASE = "https://api.elevenlabs.io"
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
ELEVENLABS_ZERO_RETENTION = False
