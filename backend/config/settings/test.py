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
AGREEMENT_CHECK_PROVIDER = "fixture"
GEMINI_AGREEMENT_MODEL = "gemini-3.8-flash"
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
ELEVENLABS_STT_MODEL = "scribe_v3"
ELEVENLABS_STT_URDU_FALLBACK_MODEL = "scribe_v2"
GROQ_API_KEY = ""
GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = GROQ_INTERPRETATION_MODEL = GROQ_AGREEMENT_MODEL = "openai/gpt-oss-120b"
GROQ_INTERPRETATION_REASONING_EFFORT = "low"
GROQ_AGREEMENT_REASONING_EFFORT = "medium"
GROQ_MAX_COMPLETION_TOKENS = 6000
