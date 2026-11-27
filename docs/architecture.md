# Kaam Madad — Architecture and Implementation Decisions

Requirements: [requirements.md](requirements.md) · Progress: [progress.md](progress.md)

**Naming.** Public brand: **Kaam Madad** (English) / **کام مدد** (Urdu), shown through the `app.name`
translation key, page metadata and the admin header. The project was formerly *Roshan Rozgaar*; internal
identifiers keep that name to avoid coordinated migrations: database name/user `roshan_rozgaar`, Compose
project `roshan-rozgaar` (container `roshan-rozgaar-db-1` and its data volume), npm package
`roshan-rozgaar-frontend`. Django apps (`apps.core`, `apps.accounts`), migrations, env keys and API routes
never contained the brand. New user-facing text must use `t("app.name")`, not a literal name.

This document records how the system is built and why. It describes what exists **now** (after M1)
and marks decisions intentionally left to later modules.

## 1. Stack (resolved versions, M1)

| Layer | Choice | Version |
|---|---|---|
| Backend runtime | Python | 3.14.0 tested (Django 6.1 requires ≥ 3.12) |
| Web framework | Django | 6.1.3 |
| API | Django REST Framework | 3.18.3 (declares Django 6.1 support) |
| Database | PostgreSQL | 18.7 (Docker image `postgres:18-alpine`) |
| DB driver | psycopg (binary) | 3.3.9 |
| Static/SPA serving | WhiteNoise | 6.12.0 |
| Local env loading | python-dotenv | 1.2.4 |
| Frontend runtime | Node.js | 24.12 tested (React Router 8 requires ≥ 22.22) |
| UI | React / React DOM | 19.3.1 |
| Routing | React Router | 8.5.2 |
| Build | Vite / @vitejs/plugin-react | 8.3.8 / 6.3.0 |
| Language | TypeScript | 7.0.2 |
| Styling | Tailwind CSS (+ @tailwindcss/vite) | 4.3.5 |
| Urdu font | @fontsource/noto-nastaliq-urdu (bundled, self-hosted) | 5.3.0 |
| Icons (M2) | lucide-react (ISC licence, tree-shaken) | 1.80.0 |
| Provider HTTP (M3) | httpx | 0.28.1 |
| Audio parsing (M3) | mutagen (pure Python) | 1.48.1 |
| Frontend tests | Vitest, jsdom, Testing Library (react, dom, jest-dom, user-event) | 5.1.1, 31.0.1, 16.3.3 / 10.4.2 / 8.0.0 / 14.6.13 |

Exact backend pins live in `backend/requirements.txt` (direct ranges in `backend/requirements.in`); exact
frontend versions live in `frontend/package-lock.json`.

Not used, by design (requirements §2): microservices, Redis, Celery, vector databases, agent frameworks,
WebSockets (polling is the MVP update mechanism).

## 2. Repository layout

```
.
├── .env.example            Backend + Docker Compose configuration template (copy to .env)
├── docker-compose.yml      Local PostgreSQL only (host port 5434 by default)
├── docs/                   requirements.md, architecture.md, progress.md
├── backend/
│   ├── manage.py           Defaults to config.settings.development ("test" → config.settings.test)
│   ├── requirements.in/.txt
│   ├── config/
│   │   ├── env.py          Typed env-var helpers (no values echoed in errors)
│   │   ├── settings/       base.py, development.py, production.py, test.py
│   │   ├── urls.py         /api/v1/, /admin/, SPA catch-all, API-aware error handlers
│   │   └── wsgi.py/asgi.py Default to production settings
│   └── apps/
│       ├── core/           Request IDs, logging filter, error envelope, exception handler,
│       │                   health endpoints, SPA view, static cache policy
│       └── accounts/       Custom User model, phone normalisation, manager, admin
└── frontend/
    ├── index.html          lang="ur" dir="rtl" by default
    ├── vite.config.ts      Dev proxy for /api, /admin, /static → Django
    ├── vitest.config.ts
    └── src/
        ├── api/            client.ts (envelope parsing, timeouts), health.ts
        ├── i18n/           Urdu/English resources, provider, types
        ├── components/     AppShell layout, inline icons, <Ltr> bidi isolation
        ├── features/health ServerStatusCard + useServerStatus
        ├── pages/          Landing, NotFound, RouteError
        └── routes.tsx      Route table (feature modules add routes here)
```

The pre-existing empty `index.py` in the repository root is a user file and is left untouched.
No code from the earlier Roshan Rozgaar prototype (the project's former name) was used.

## 3. Runtime topology

**Development** — two processes, one browser origin:

```
Browser ──► http://localhost:5173 (Vite dev server)
              ├── /src, /@vite, assets ──► served by Vite (hot reload)
              └── /api, /admin, /static ──► proxied to Django http://127.0.0.1:8000
Django ──► PostgreSQL 127.0.0.1:5434 (Docker Compose)
```

The proxy keeps the browser's `Host` header (`changeOrigin: false`), so Django sees the same origin as the
page and session/CSRF cookies behave as in production.

**Production** — one Django deployment serves everything from one origin:

| Path | Served by | Caching |
|---|---|---|
| `/api/v1/...` | DRF views | API responses as set per view (health: `no-store`) |
| `/admin/...` | Django Admin | — |
| `/static/...` | WhiteNoise, from `collectstatic` (manifest-hashed) | immutable, 10 years |
| `/assets/...`, `/favicon.svg` | WhiteNoise, from `frontend/dist` (`WHITENOISE_ROOT`) | hashed files immutable; others revalidated |
| any other path | `spa_index` view → `frontend/dist/index.html` | `no-cache` so new deploys load immediately |

Unknown `/api/...` paths always return the JSON 404 envelope and never fall through to the SPA.
The WSGI server choice (e.g. gunicorn on Linux) and HTTPS termination are decided in M11.

## 4. Backend decisions

### Settings
- `base.py` holds everything shared; `development.py` (DEBUG, insecure fallback key, local hosts),
  `production.py` (fail-fast checks, HTTPS, secure cookies, HSTS, manifest static storage),
  `test.py` (development + fast MD5 hasher for tests only).
- Production **refuses to start** without a ≥ 50-character non-`django-insecure` `DJANGO_SECRET_KEY` or
  without `DJANGO_ALLOWED_HOSTS` (covered by subprocess tests).
- The repository-root `.env` is loaded with `override=False`: real environment variables always win.
- `TIME_ZONE = "Asia/Karachi"`, `USE_TZ = True`: timestamps stored in UTC, displayed in Karachi time.
- `POSTGRES_HOST` defaults to **`127.0.0.1`, not `localhost`**. Measured on Windows + Docker Desktop:
  with `localhost`, libpq tries IPv6 `::1` first, where the published port hangs until
  `connect_timeout` — adding ~5 s to *every* new connection and ~10 s to a failed readiness check.
  With `127.0.0.1`: connect ≈ 0.05 s; readiness failure ≈ 3.3 s (timeout 3 s).

### Custom user model (`apps/accounts`)
Defined before the first migration (`accounts.0001_initial`).

| Field | Notes |
|---|---|
| `id` | UUID4 primary key — opaque external identifier |
| `phone_number` | Login identity (`USERNAME_FIELD`), unique, stored as E.164 `+923XXXXXXXXX` |
| `role` | `worker` / `customer`; empty for staff-only accounts. **Grants no staff permission.** |
| `preferred_language` | `ur` (default) / `en` |
| `is_active` | Standard Django active flag |
| `is_demo` | Fictional/test account marker for labelling and separation (NFR-04) |
| `is_staff`, `is_superuser`, groups, permissions | Standard Django — the only source of staff authority |
| `date_joined`, `updated_at`, `last_login`, `password` | Standard; passwords hashed by Django (PBKDF2 default) |

- **Phone normalisation** (`apps/accounts/phone.py`) accepts what people type — `0300 1234567`,
  `+92 300 1234567`, `00923…`, `3001234567`, Urdu/Arabic-Indic digits, invisible bidi marks — and accepts
  **mobile numbers only** (the future OTP target). Applied in the manager, `clean()`, `save()`, admin forms,
  admin search, and `get_by_natural_key` (so login works with any format).
- **Database constraints** enforce the invariants even if Python validation is bypassed: phone regex
  `^\+923[0-9]{9}$`, valid role set, valid language set, unique phone. Verified with `\d accounts_user`.
- **Masking**: `str(user)` and admin lists show `+92 3** ***4567`; the full number appears only on a user's
  own admin change page.
- CNIC is never a username or login field.
- Planned additions (later modules, via migrations): restricted state and phone-confirmation method
  (M2/M10). Role immutability after signup is enforced in the M2 signup/profile API.

### API conventions (`apps/core`)
- Prefix `/api/v1/`. JSON only (JSON renderer/parser).
- **Default deny**: `IsAuthenticated` + `SessionAuthentication` globally; public endpoints opt in.
- **Error envelope** (requirements §10), produced by `api_exception_handler` and the API-aware Django
  `handler400/403/404/500`:

  ```json
  {"error": {"code": "validation_error", "message": "Some submitted values are invalid.",
             "request_id": "…", "fields": {"items.1.amount": [{"code": "invalid", "message": "…"}]},
             "details": {"…": "non-sensitive context, e.g. current state for a 409"}}}
  ```
  `code` is stable and drives client translations; `message` is an English fallback; `fields` appears
  only for validation errors (nested errors flattened to dotted paths); `details` is optional.
  Exception text, SQL, stack traces and credentials never appear in responses.
- Application errors raise `ApiError(message, code, details=…, status_code=…)`.
- **Request IDs**: a server-generated UUID per request, in `X-Request-ID`, in every error body, and in every
  log line (client-supplied IDs are ignored to prevent spoofing/log injection).
- **Health**:
  - `GET /api/v1/health/live/` → `200 {"status":"ok"}`. No database, session or auth access (asserted with
    zero queries).
  - `GET /api/v1/health/ready/` → `200 {"status":"ok","checks":{"database":"ok"}}`, or
    `503` envelope `service_not_ready` with `details.checks.database = "unavailable"`. The failure is
    logged by exception class name only. Both are `Cache-Control: no-store` and exempt from the HTTPS
    redirect (platform probes).

### Admin
`UserAdmin` with phone-aware creation/change forms, masked list display, filters (role, active, staff,
superuser, demo, language), and search that normalises a full phone number in any format. Header:
"Kaam Madad staff administration". Marketplace users without `is_staff` are redirected to the admin
login (tested).

### Media
`PRIVATE_MEDIA_ROOT` (`backend/private_media/`, git-ignored) is configured as `MEDIA_ROOT` but **no URL
serves it**. M3 adds authorised download views (MEDIA-01).

## 5. Frontend decisions

- **Mobile-first shell**: single column, `max-w-lg`, 16 px gutters; verified with Chrome DevTools-protocol
  device emulation at **360 px**: no horizontal overflow in Urdu or English.
- **i18n structure** (`src/i18n`): Urdu resource is the source of keys; English is type-checked for
  parity (`Record<TranslationKey, string>`) and tested at runtime. `I18nProvider` sets
  `<html lang dir>`, defaults to Urdu/RTL, persists the choice in `localStorage` (guarded). The visible
  language switch and server-side preference sync are **M2**.
- **RTL/Urdu rendering**: Noto Nastaliq Urdu (Arabic-script subset, 400/700, ~160 KB woff2 each) is bundled
  and self-hosted; Latin text uses the system font. Urdu gets larger text and taller line heights by
  overriding Tailwind's `--text-*--line-height` variables under `html:lang(ur)`. Layout uses logical
  (start/end) properties. `<Ltr>` (`<bdi dir="ltr">`) isolates numbers, codes and IDs inside Urdu text.
- **Accessibility baseline**: skip link, visible focus ring, `role="status"` + `aria-live` for async
  state, icon + text on every action, 44 px minimum touch targets (retry button measured at 52 px).
- **API client** (`src/api/client.ts`): same-origin `fetch` with credentials, 10 s timeout, caller
  cancellation. Errors are `ApiError` (envelope from Django: code, requestId, fields, details) or
  `ConnectionError` (`offline` / `timeout` / `unreachable`, including non-envelope 5xx from a
  proxy/gateway, e.g. Vite's 502 when Django is down). CSRF header handling for mutations arrives with
  authentication in M2.
- **Landing screen**: identifies the product, states plainly that registration/requests/bookings are not
  available yet, and shows live readiness: checking → ready / database unavailable (with reference
  number) / offline / timeout / unreachable / unexpected, with a retry action. No fake lists or simulated
  integrations.

## 6. Security posture after M1

- Secrets only in environment variables; `.env`, `.env.*` (except `.env.example`), private media,
  virtualenvs, `node_modules`, build output and `staticfiles` are git-ignored.
- Production: HTTPS redirect, `Secure` + `HttpOnly` session cookie, `Secure` CSRF cookie, `SameSite=Lax`,
  HSTS (3600 s default, configurable), nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`.
- `check --deploy` with production settings reports only HSTS include-subdomains/preload (domain decisions
  for M11) and, in the local HTTP smoke test only, the deliberately disabled SSL redirect.
- Logs carry request IDs and never driver error messages from readiness checks.

## 7. Decisions deferred (and where)

| Topic | Module |
|---|---|
| Real SMS/OTP provider integration (boundary exists; see §8) | Before a real pilot |
| Password policy suited to low-literacy users (Django defaults still apply) | Revisit with user testing |
| Restricted account state beyond `is_active`, user blocking | M10 |
| Verified area centre coordinates (needed for approximate distance) | M6 |
| CNIC OCR implementation, verification cases, staff review queue (boundaries exist; see §9) | M4 |
| Staff access to private audio with audit logging (no admin access to audio yet) | M10 |
| Content-Security-Policy (needs browser verification of admin + SPA), WSGI server, HTTPS deployment, HSTS subdomains/preload | M11 |

## 8. Module M2 — accounts, language, catalog

API contracts: [api.md](api.md).

### Authentication and sessions
- Endpoints `auth/csrf`, `auth/signup`, `auth/login`, `auth/logout`, `auth/me`, `auth/me/language` (the only
  editable profile field). Django `login()`/`logout()`; login rotates the session key (fixation-tested) and the
  CSRF token. Sessions last 14 days (`SESSION_COOKIE_AGE`), HttpOnly, `SameSite=Lax`, `Secure` in production.
- `CsrfEnforcedSessionAuthentication` (`apps/accounts/authentication.py`) replaces DRF's session auth: CSRF is
  enforced on **every** unsafe request, including anonymous signup/login (DRF's default skips anonymous CSRF),
  and missing sessions return **401** `not_authenticated` instead of 403. The CSRF cookie is readable by JS
  (`CSRF_COOKIE_HTTPONLY = False`) so the SPA can echo it; the session cookie is not.
- Strict serializers reject unknown fields (`unexpected_field`), so signup cannot set staff flags, demo flag,
  verification or restriction state; the language endpoint cannot change `role`. `role` has no update path.
- Suspension = `is_active=False`: Django refuses login and drops the user from existing sessions on the next
  request (tested). `account_inactive` is only revealed to someone who supplies the correct password.
- Role permissions: `IsMarketplaceUser`, `IsWorker`, `IsCustomer` (`apps/accounts/permissions.py`) — staff
  authority never implies a marketplace role.
- Rate limits: DRF throttles reading `settings.API_THROTTLE_RATES` at request time; counters in a PostgreSQL
  `DatabaseCache` table (`app_cache`, created by migration `core.0001`) so limits hold across processes without
  Redis. Per-IP limits are generous for shared venue networks; login is also limited per phone number (hashed
  key). `DJANGO_NUM_PROXIES` (default 0) prevents X-Forwarded-For spoofing.

### Deployment mode and phone confirmation (AUTH-03, NFR-04)
- `APP_DEPLOYMENT_MODE` = `live` | `demo` (development default `demo`, production default `live`). Demo
  deployments flag new accounts `is_demo` and the UI shows a persistent demo banner (from `GET /config/`).
- `PHONE_VERIFICATION_PROVIDER` = `demo` | `unconfigured`. `check_simulation_allowed()` raises
  `ImproperlyConfigured` at settings load when `demo` is combined with `live` — production cannot start with
  simulated authentication (subprocess-tested). The service re-checks at runtime.
- **Provider boundary** (`apps/accounts/phone_verification.py`): the server generates the code, stores only an
  HMAC-SHA256 digest (keyed by `SECRET_KEY`, bound to challenge id, purpose and phone), and calls
  `PhoneCodeSender.send_code()`. `DemoPhoneCodeSender` sends nothing and allows the code to be returned once in a
  labelled demo response; `UnconfiguredSmsSender` raises `phone_verification_unavailable` (no challenge stored,
  nothing pretended). **To add a real SMS provider:** implement `send_code` (call the API with a timeout, return
  its message id as `provider_reference`, raise `PhoneVerificationUnavailable` on failure), register it in
  `get_phone_code_sender()` under a new setting value, and keep secrets in environment variables. Providers
  that generate their own codes (verify-style APIs) would need a variant that delegates the check step too.
- Status vs method: `User.phone_confirmed_at` (status) and `User.phone_confirmation_method` (`demo`/`sms`) are
  separate fields with a DB constraint keeping them consistent. The UI labels a demo confirmation "Demo
  confirmation (not real verification)".
- `PhoneVerificationChallenge`: partial unique constraint = at most one open code per user and purpose; check
  constraints bound attempts and expiry. Failed attempts are committed before the error is returned; issuing
  and verifying lock rows (`select_for_update`) so limits cannot be raced. Policy: 10-minute expiry, 5 attempts,
  60 s resend cooldown, 5 codes/hour.

### Catalog (`apps/catalog`)
- Models: `Trade` → `ServiceTag`; `City` → `Area` (`kind` sector/locality, optional approximate centre, left
  empty until verified); `SpecialityQuestion` (three global questions whose prompts take `{trade}`; choices are
  the trade's active service tags, `choice_source` says whether a question draws from all services or from the
  "offered" answers). Consistency rules (offered ∩ not-offered = ∅; primary ⊆ offered) live in
  `apps/catalog/speciality.py` and are returned to clients as `rules`.
- Every entry: stable `code` (validated slug, unique), Urdu + English labels, `is_active`, `sort_order`;
  foreign keys `PROTECT` (deactivate, don't delete). Icons are a controlled vocabulary shared with the frontend
  (`icons.py` ↔ `catalogIcons.tsx`, checked by a frontend test).
- `python manage.py seed_catalog [--dry-run]`: upserts by code, never deletes, leaves unrelated staff-created
  records alone, preserves an existing record's `is_active`, touches no user/identity data. Seeds 3 trades,
  23 services, 2 cities, 19 sample areas (11 Islamabad, 8 Rawalpindi), 3 questions. Areas are samples, not
  coverage claims; coverage is not tied to a fixed sector list.
- Admin: trades with inline services, services, cities, areas, questions (filters, search, inline
  ordering/activation). Phone challenges are read-only in admin and never show the digest.

### Frontend
- `AuthProvider` boots with `GET /auth/csrf/`, `/config/`, `/auth/me/` in parallel; failure → error state with
  retry (no infinite spinner). States: loading, error, anonymous (`sessionExpired` / `loggedOut`),
  authenticated. Any later 401 → "session ended" → login page with `?expired=1` and `?next=`.
- Guards: `RequireAuth role=…` (anonymous → login with `next`; wrong role → own home; logged out → landing) and
  `GuestOnly` (users already signed in on arrival → home; users who sign in on the page are left to the form, so
  signup → phone confirmation and login → `next` are not raced — both were real bugs found in browser testing).
  `next` accepts only same-site paths.
- **Language rule**: anonymous → device setting (`localStorage`); signup sends the language on screen; after
  login or session restore the **account preference is applied**; switching while signed in updates the UI at
  once and `PATCH`es the account (if that fails the device keeps the choice and the account value applies at
  next login). `<html lang dir>` is set in a layout effect so text and direction change in the same frame.
- API client: mutations send `X-CSRFToken` from the cookie; `csrf_failed` triggers one token refresh + retry.
- Reusable UI (`src/components/ui`): `Button`/`ButtonLink` (48 px, icon + text, loading), `TextField`,
  `PasswordField` (show/hide), `FieldErrors`, `IconTileGroup` (radio or multi-select semantics, selected state
  shown by border + check icon + "Selected" text), `LanguageSwitch`, `StatusBadge`, `Alert`, `PageLoader`,
  `AudioButton` (renders nothing without a source/handler; readable fallback on failure).
- Server error codes and field codes map to `errors.*` / `fieldErrors.*` translation keys
  (`src/i18n/errors.ts`); English is type-checked against Urdu for key parity.

## 9. Module M3 — audio and AI adapters

API contracts: [api.md § Voice and AI](api.md#voice-and-ai-m3).

### Provider choices (checked against current documentation, 25 Nov 2026)

| Capability | Real provider | Model / voice | Why |
|---|---|---|---|
| Speech-to-text | **Google Gemini API**: audio understanding via the Interactions API | `gemini-3.8-flash` (stable; `GEMINI_STT_MODEL`) | Accepts WAV/MP3/M4A/AAC/OGG/Opus/FLAC/WebM inline (≤ 20 MB request); one key also covers interpretation; free AI Studio tier for live checks. Prompted for a verbatim transcript in the spoken language: Urdu script, English trade terms kept as spoken, negations kept. |
| Interpretation | **Google Gemini API**: structured output (`response_format` with a JSON schema) | `gemini-3.8-flash` (`GEMINI_INTERPRETATION_MODEL`) | Reuses the speech-to-text provider and key ("reuse where it meets the requirements"). Output is re-validated on the server regardless. |
| Text-to-speech | **Azure AI Speech** neural TTS REST | `ur-PK-UzmaNeural` (Urdu), `en-IN-NeerjaNeural` (English), `riff-24khz-16bit-mono-pcm` | The Gemini API speech-generation language table does **not** list Urdu (only Hindi), so Gemini TTS does not meet the requirement. Azure has ur-PK neural voices. |
| Text-to-speech (alternative, added 26 Nov 2026) | **ElevenLabs** text-to-speech REST | `eleven_v3` (`ELEVENLABS_MODEL_ID`), one voice `ELEVENLABS_VOICE_ID` for Urdu and English, `mp3_44100_128` | Selected with `TEXT_TO_SPEECH_PROVIDER=elevenlabs`. ElevenLabs lists "Urdu (ur)" for Eleven v3; Multilingual v2 and Flash v2.5 do not list Urdu, so those models are not suitable. The docs now call v3 the "previous generation" and recommend testing Eleven v4. |

Documentation facts relied on (Gemini docs at aistudio.google.com/docs, redirected from ai.google.dev): endpoint
`POST https://generativelanguage.googleapis.com/v1beta/interactions`, header `x-goog-api-key`, example header
`Api-Revision: 2026-05-20`; input parts `{"type":"text"}` and `{"type":"audio","data":<base64>,"mime_type":...}`;
`system_instruction`; `response_format: {"type":"text","mime_type":"application/json","schema":{...}}`;
`generation_config.max_output_tokens`; `store: false` disables server-side storage of the interaction; Gemini 4
and 3.6+ ignore temperature (so none is sent); errors 401 `authentication`, 429 `rate_limit_exceeded` /
`quota_exceeded`, 503 `service_unavailable`. **Caveat:** the docs show the SDK field `output_text` and the
`steps[]` / `type: "model_output"` / `content[]` structure but no raw JSON response sample. The adapter accepts
both forms and otherwise fails closed (`ai_output_invalid`). This is the first thing to confirm in a live check.
Azure (learn.microsoft.com): `https://{region}.tts.speech.microsoft.com/cognitiveservices/v1`,
`Ocp-Apim-Subscription-Key`, `Content-Type: application/ssml+xml`, `X-Microsoft-OutputFormat`, `User-Agent`;
401/429/502/503 documented; audio longer than 10 minutes is truncated.
ElevenLabs (elevenlabs.io/docs, 26 Nov 2026): `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` with
header `xi-api-key`, query `output_format` (default `mp3_44100_128`; 44.1 kHz PCM/WAV needs a Pro plan), JSON
`{"text", "model_id", "language_code"}` (`language_code` is ISO 639-1 and is ignored if the model does not support
it); `eleven_v3` allows 5,000 characters per request (we cap at 1,500); `enable_logging=false` (zero retention) is
enterprise-only, so by default generated speech stays in the account history. Errors arrive as
`{"detail": {"status": <code>}}`: `quota_exceeded` → `ai_provider_limit_reached` (it is not a credentials problem
even though it can come with 401), `too_many_concurrent_requests` → limit, `system_busy` → unavailable,
`invalid_api_key` / `voice_not_found` → not configured. The adapter accepts only MP3 or WAV output and checks the
magic bytes; the file is stored as `.mp3` or `.wav` and served with its real type.

### Structure

- `apps/providers/`: capability adapters, independent of Django models.
  `speech_to_text.py`, `interpretation.py`, `text_to_speech.py` (each with real, `fixture` and `unconfigured`
  implementations), `gemini.py` (shared client), `http.py` (timeouts, retries, error mapping), `errors.py`
  (taxonomy), `registry.py` (selection and `/config/` status), `identity.py` (OCR and identity-verification
  boundaries only).
- `apps/voice/`: private audio and drafts. Models `AudioClip`, `Transcription`, `Interpretation`,
  `SpeechSynthesis`; `audio.py` (server validation), `drafts.py` (schemas, catalog mapping, negation,
  corrections, confirmation), `services.py` (orchestration and reuse), `views.py`, `urls.py`.
- Settings: `SPEECH_TO_TEXT_PROVIDER`, `INTERPRETATION_PROVIDER`, `TEXT_TO_SPEECH_PROVIDER` (development default
  `fixture`, production default `unconfigured`). `check_simulation_allowed()` refuses `fixture` unless
  `APP_DEPLOYMENT_MODE=demo` (at startup, subprocess-tested), and the registry treats fixture as unconfigured in
  live mode (at runtime). Keys live only in environment variables; `/config/` exposes availability, never keys.

### Reliability (AI-03, NFR-02)

- Per-attempt timeout `AI_PROVIDER_TIMEOUT_SECONDS` (20 s) and `AI_PROVIDER_MAX_RETRIES` (1) with backoff for
  timeouts, network errors and 500/502/503/504. 429 is never retried (it is a usage limit); 401/403 mean "not
  configured". The frontend allows 60 s for AI calls.
- Reuse instead of reprocessing: transcription per clip + provider + model + hint; interpretation per owner +
  text + kind + language + provider + model + catalog fingerprint; synthesis per owner + text + language + voice.
- Limits in one place (`VOICE_LIMITS`): 10 MB and 60 s (+0.25 s tolerance) per clip, at least 0.3 s, 4000
  characters to interpret, 1500 to synthesise.

### Safety of AI output (AI-02, AI-04, DATA-02)

- Prompts declare the transcript untrusted data and forbid following instructions inside it; the transcript is
  wrapped in markers. Whatever the model returns, only the draft fields defined in `drafts.FIELD_TYPES` can be
  produced, and nothing in M3 publishes a profile, creates a job, or changes permissions or identity status.
- `validate_raw` enforces types (wrong types give `ai_output_invalid`, and nothing is stored). `build_draft`
  keeps only active catalog codes, separates negated mentions, removes services said both ways, drops a name that
  is not in the source text, and computes `missing` and `uncertain` deterministically.
- Stored separately: the original transcript (`Transcription.text`, `Interpretation.source_text`), the model
  draft (`draft`), the user's corrections (`corrections`) and the confirmed result (`confirmed_fields`).

### Private media (MEDIA-01, SEC-02, SEC-04)

- Files go to `MEDIA_ROOT = PRIVATE_MEDIA_ROOT` with random names (`audio/YYYY/MM/<uuid>.wav`): no user IDs and
  no client file names. No URL route serves the folder; every download checks ownership in the view and returns
  `private, no-store`. The frontend fetches audio as a blob (this works with the session cookie and avoids
  Safari range-request problems) and plays it from an object URL.
- Logs carry the provider name, status and reason only, never audio, transcripts or synthesis text (tested).
- No Django Admin access to audio or transcripts in M3: staff access to evidence needs audit logging (M10).

### Frontend

- `useRecorder` records with `getUserMedia` and Web Audio and encodes **16 kHz mono 16-bit WAV in the browser**
  (about 1.9 MB per 60 s), so every browser produces the same verifiable format. Permission is requested only
  when the user presses "Record", and recording stops automatically at 60 s. Recording needs a secure context
  (HTTPS or localhost): phones opening the dev server over plain http on the LAN get the upload and typing
  fallbacks instead.
- Components: `VoiceCapture` (record, stop, replay, upload, client-side size and duration checks),
  `DraftEditor` (read-only transcript; every field editable; "Missing" and "Please check" badges; unmatched
  mentions with their negation; overlap warning), `ReadAloud` (text always visible; failure shows the reason
  and a retry), `SimulatedBadge`, `TextArea`. The `/voice-test` page (signed-in users) runs the full flow for
  both kinds.
- Errors are stored as error objects or codes and translated at render, so messages follow a language switch.
  This also fixed the same issue on the M2 login, signup and phone pages.

### M4 handoff: CNIC OCR and identity verification (ID-01 to ID-04) — superseded, see §10

`apps/providers/identity.py` defines `CnicOcrProvider.extract()` and `IdentityVerificationProvider.verify()` with
only `Unconfigured*` implementations. M3 exposes no CNIC endpoint and accepts no CNIC upload. For M4:

1. Store CNIC images like audio: private storage, random names, owner/staff-only downloads, never message
   attachments or public assets, never logged. Validate JPEG/PNG/WebP content and size on the server.
2. Implement an OCR provider behind `CnicOcrProvider` (a vision-capable Gemini model is a candidate and would reuse
   the same adapter pattern and `ai_*` error codes). OCR output is a draft: the worker confirms or corrects it;
   deterministic format checks (13-digit CNIC, expiry date) run in code; OCR success never changes status.
3. Identity verification: a `VerificationCase` model with status (draft/pending, needs correction, provider
   verified, manually reviewed, demo approved, rejected/expired/suspended), method, reviewer, reason and consent.
   Real NADRA verification only with authorised access and a contract; keep `UnconfiguredIdentityVerification`
   until then. Manual staff review and demo approval are separately labelled methods; nothing is ever labelled
   "NADRA verified" without the real provider.

## 10. Module M4 — worker onboarding and identity check

API contracts: [api.md § Workers and identity](api.md#workers-and-identity-m4). Requirement changes:
[requirements.md § M4 amendments](requirements.md#m4-amendments-27-nov-2026).

### Onboarding (`apps/workers`)

- `WorkerProfile` stores the worker's own declarations: the trade, the services offered, one main speciality,
  the services not offered, a city and the service areas. It also stores `accepting_requests`, the worker's
  own choice, which is separate from completion and identity.
- `onboarding.py` reuses the catalog rule set (`apps.catalog.speciality.validate_speciality_answers`: unknown
  or other-trade services, offered ∩ excluded, main ⊆ offered) plus the selection limits stored on
  `SpecialityQuestion` (the main speciality is exactly 1). It also checks that each area belongs to the chosen city.
- **Completion is never stored:** `onboarding_state()` recomputes it from the saved data and the live catalog,
  so a deactivated service makes a profile incomplete again. Each `PUT` saves one screen, so the frontend
  resumes at `next_step` after a refresh or login.
- **Screens:** screen 1 is the M2 signup (worker preselected from "مجھے کام چاہیے"); screens 2 and 3 are
  `/worker/setup/work` and `/worker/setup/areas`. `/worker` redirects there until the profile is complete.
- **No location:** there is no geolocation code; areas are chosen manually from the catalog.

### Identity: real OCR, simulated registry

1. **Scan:** `apps.workers.identity.scan_card`.
   1. Validate the photo before any OCR: magic bytes, then Pillow decodes the header and checks that the
      format matches. It must be ≤ 5 MB, at least 400 × 250 px and at most 40 MP; `verify()` catches truncated
      files.
   2. `TesseractCnicOcr` (`apps/providers/identity.py`) prepares the image: EXIF orientation, grayscale, about
      1800 px wide, autocontrast and sharpening.
   3. It writes the image to a private `TemporaryDirectory` and runs
      `tesseract <png> stdout -l eng --psm 6` with the remaining budget (`OCR_TIMEOUT_SECONDS`, default 20 s).
      If both fields are not found, it retries rotated 90°, 270° and 180°. The folder is deleted on exit.
   4. Parsing extracts exactly one 13-digit candidate (dashes and spaces optional, `O` read as `0`), and the
      value of the holder's labelled **Name** field ("Father Name" is skipped). Missing or ambiguous → `None`.
      Raw text is never stored, logged or returned.
   5. The image is **not retained**.
2. **Review:** only the two extracted fields are held, as the owner's draft (`ocr_name_pending`,
   `ocr_number_pending`). The worker edits them in a keyed review form; whether each submitted value differs from
   the scan is stored (`name_corrected`, `number_corrected`).
3. **Registry:** `DemoRegistryVerification` looks up the keyed digest of the number (`salted_hmac`), then compares
   the normalised name (case and spacing) with the **same** record → `match` / `name_mismatch` / `no_record`.
   - Only `match` sets `demo_approved` with method `demo_registry`, a timestamp and the registry reference.
   - Stored: the masked number `*****-*****67-1` and the digest; the draft is cleared.
   - A submit needs a processed scan (read, partial or unreadable), so a typed-only approval without a scan is
     impossible. If Tesseract is missing, nobody can verify, which is the intended "setup error".
4. **Demo-only rule:**
   - `IDENTITY_VERIFICATION_PROVIDER=demo_registry` is refused at startup unless `APP_DEPLOYMENT_MODE=demo`
     (`check_simulation_allowed`), and is replaced by the unconfigured provider at runtime in live mode.
   - `seed_demo_registry` refuses to run in live mode.
   - NADRA stays `UnconfiguredIdentityVerification`.
5. **Staff:** a read-only Django Admin for `IdentityVerification` shows status, method, the OCR source
   (`tesseract (read)`), the registry source (`demo_registry (demo, fictional)`), the masked number and the
   reference. It never shows the digest or the draft, and there is no image to show.

### Eligibility (shared check)

`apps.workers.eligibility.worker_eligibility(user)` →
`Eligibility(can_take_jobs, receives_requests, reasons)`.

**Rules:**
- Worker role.
- `is_active`.
- `onboarding.is_complete`.
- Identity status `provider_verified` or `manually_reviewed`, or `demo_approved` **only in demo mode**.
- `receives_requests` additionally requires `accepting_requests`.
- Phone confirmation is not part of eligibility.

**Callers (to be wired by later modules):**
- **M6 recommendations:** list only workers whose `receives_requests` is true, and re-check before sending an
  invitation.
- **M8 booking finalisation:** call `can_take_jobs` inside the booking transaction after locking the worker
  row, and refuse to confirm if it is false. A paused worker can still finish existing bookings.

### Fixed instruction audio (UX-03)

`apps/voice/instructions.py` holds four fixed Urdu/English sentences.
`GET /instructions/{key}/audio/` synthesises each key/language/voice once (`InstructionAudio`) with the
configured TTS provider. The client sends only the key, so passwords, codes and CNIC numbers can never reach
speech synthesis. The frontend `InstructionAudio` component always shows the text and offers the play button
only when TTS is available.

## 11. Module M5 — customer job requests

API contracts: [api.md § Job requests](api.md#job-requests-m5).

### Model and lifecycle (`apps/jobs`)

- `JobRequest` belongs to one customer (`customer` FK from the session). It keeps the **original input**
  (`original_text` set once, plus owned references to the `AudioClip`, `Transcription` and `Interpretation`)
  separately from the **confirmed details**:
  - description, trade, services and services not needed, city, area;
  - `preferred_time_text` as said, and the UTC window `window_start`/`window_end`;
  - private `address_private` and `access_notes`;
  - `budget_pkr` (decimal, the customer's preference).
- Status is `draft` → `confirmed`. Database constraints require the trade, city, area and window once confirmed,
  `window_end > window_start` and a non-negative budget.
- **Draft first:** the frontend creates the draft before calling speech-to-text or interpretation, so
  provider errors and reloads never lose the input. `POST /jobs/{id}/source/` attaches the customer's own
  transcript or interpretation and fills only empty fields with suggestions that pass the rules.
- **Rules:** `rules.check()` holds the relationship and window rules (always) and the required fields (on
  confirmation only). A `PATCH` that breaks a rule saves nothing. Confirmation runs under `select_for_update`
  and is idempotent.
- **Time:** the UI takes a Karachi date and start/end times and sends `…+05:00` (Pakistan has no DST). The server
  also reads naive times as Asia/Karachi, stores UTC and rejects past windows and windows more than 90 days
  ahead. The UI formats with `Intl` in `Asia/Karachi`.

### Privacy

- **Ownership:** all queries are scoped to `customer=request.user`, so another customer's IDs are `404`;
  `IsCustomer` keeps workers out.
- **Photos:** `photos.clean_photo` validates the content, applies the EXIF orientation and **re-encodes**
  without metadata (removing GPS). Files are stored privately with random names; downloads are checked against
  the owner and served `private, no-store`. Photos never reach AI.
- **Read aloud:** it speaks only the work, area, date and time (`speechText`). The address and access notes never
  reach speech synthesis; the server also strips invisible bidi marks before synthesis.
- **Matching:** `summary.matching_summary(job)` is the only shape M6 should use to show a request to workers.
  It leaves out the address, access notes, photos and original audio.

### M6 hand-off

A confirmed `JobRequest` has validated `trade`, `services` (plus `services_excluded`), `city`/`area` and a UTC
window. M6 should:
- match on these fields together with `apps.workers.eligibility.worker_eligibility(...).receives_requests`;
- read requests through `matching_summary`;
- add invitations without changing the confirmed request.

## 12. Module M6 — recommendations and targeted invitations

API contracts: [api.md § Recommendations and invitations](api.md#recommendations-and-invitations-m6).

### Matching (`apps/invitations/matching.py`)

- **Input:** `matching_summary(job)` only, i.e. the customer-confirmed trade, services, area and window. M5
  already mapped words to catalog choices, so M6 makes **no AI call** (REC-02 "rules first").
- **Filtering:**
  - A database pre-filter on trade, area and an active worker account.
  - `match_profile()` then requires every requested service to be offered, and none of them to be listed as
    not offered.
  - Finally `worker_eligibility(...).receives_requests` must be true. It is the single source for profile
    completeness, identity status (demo approval only in demo mode), account state and the worker's
    accepting-requests choice.
- **Ranking:**
  - Key: `(-|requested ∩ main specialities|, worker_id)`.
  - The tie-breaker is the profile's random UUID, so the order is stable across calls and not biased towards
    older or newer accounts. New workers stay eligible.
  - Reviews, completed-job history, overlapping reservations and approximate distance are deferred to M8/M9,
    and no distance is shown.
- **Explanations:** each card lists stored facts only (`speciality`, `offers`, `serves_area`). It also shows
  the identity status (labelled "demo only" when simulated) and "new: no completed jobs or reviews yet".
  Services and specialities are labelled as the worker's own declarations.

### Invitations (`apps/invitations`)

- **`Invitation`:**
  - Fields: UUID, `job`, `worker_profile`, `status` (`active`/`declined`/`withdrawn`), `shared_summary`,
    `created_at`, `seen_at`, `closed_at`, `decline_reason`.
  - `shared_summary` is the `matching_summary(job)` taken at send time. It is what the worker sees, and an audit
    of what was shared.
- **One active invitation per request (JOB-06):**
  - The database enforces it with the partial unique index `inv_one_active_per_job` (`status='active'`).
  - `send_invitation()` first takes `SELECT … FOR UPDATE` on the job, so concurrent sends queue up.
  - A send to the same worker returns the existing invitation. A send to a different worker is
    `409 invitation_already_active`. An `IntegrityError` backstop maps to the same answers.
  - `TransactionTestCase` threads on PostgreSQL prove it: four racing sends give one active invitation, and
    three racing retries give one invitation.
- **Re-check on send:** the target must still match and still be eligible
  (`400 worker_id: worker_not_available`).
- **Lifecycle:** decline (worker) or withdraw (customer) close the invitation and free the slot. Closed rows are
  history, and re-inviting creates a new ID.
- **Description edit:** `PATCH /jobs/{id}/shared-description/` lets the customer edit the free-text description
  of a confirmed request only while no invitation is active. `privacy_warnings()` (`apps/jobs/summary.py`)
  flags phone-number-like and address-like text in Urdu and English, as a reminder rather than a guarantee.
- **Privacy:** worker endpoints return only `shared_summary` without the job ID. M5's owner-only job and photo
  endpoints are unchanged.
- **Demo data:** `seed_demo_workers` (demo mode only) creates four fictional workers for rehearsals.

### M7 hand-off

An active `Invitation` (stable UUID) ties one confirmed job to one worker. M7 should hang the private
conversation and quotations off `Invitation.id`. It should close sending when the invitation is declined or
withdrawn (JOB-06), and re-check `worker_eligibility` before anything that commits either party.

## 13. Module M7 — private conversation, quotations and agreement gaps

API contracts: [api.md § Conversations, quotes and agreement gaps](api.md#conversations-quotes-and-agreement-gaps-m7).

### Conversation (`apps/conversations`)

- **Keyed by `Invitation.id`.** `participation()` returns `(invitation, role)` only for the job owner or the
  invited worker; everyone else gets `404`.
  - Writes call `require_active()` (`409 conversation_closed`) inside the transaction, after the invitation row
    is locked.
  - Reads work in every status, so history survives a decline or withdrawal (JOB-06).
- **`Message`:**
  - Fields: `invitation`, `sender`, `sender_role`, `client_id`, `kind` (`text`/`voice`), `text`,
    `caption_status`, `interpreted_text`, `audio_clip`, `transcription`, `created_at`.
  - Messages are immutable, and there is no edit or delete endpoint.
  - Constraints:
    - `msg_client_id_once (invitation, sender, client_id)` makes a retried send return the stored message
      (`200`). An `IntegrityError` backstop covers two concurrent retries.
    - `msg_clip_once` means a clip belongs to one message.
    - `msg_kind_consistent` means a text message has no clip and a voice message has one.
- **Voice notes (MSG-01, MSG-03):**
  - The clip uses M3's private audio store with its own purpose `message`, and stays owner-only until sent.
  - M3's transcription proposes a caption. The **sender** reviews or edits it, and only the approved `text`
    goes to the other side.
  - The proposal (`interpreted_text`) is kept for the sender and audit, separate from the original audio and
    the approved caption.
  - With no caption, `caption_status="unavailable"` and both sides see "Caption unavailable".
  - Playback (`…/messages/{id}/audio/`) is checked through `participation()` and sent with
    `Cache-Control: private, no-store`.
- **Pagination and polling:** pages of 30, newest first, plus the `after`/`before` cursors. The client polls
  `after=<last id>` every 5 s, appends only, and never resets the composer.
- **Job context:** the header returns `shared_view(invitation.shared_summary)`, the same text the worker was
  shown in M6. Only the customer also gets `job_id`, for the link back. M5's owner-only job, photo and draft
  endpoints are unchanged.

### Quotations

- **`Quote`:**
  - Fields: version, status `draft`/`submitted`/`superseded`, `inspection_only`, `scope`, `quantity`,
    `labour_amount` with `labour_basis` `total`/`per_item`, `materials` (`included`/`worker_extra`/`customer`/
    `none`), `materials_amount`, `visit_fee` with `visit_fee_treatment`, `exclusions`, `start_at`/`end_at`,
    frozen `totals`, `submitted_at`, `superseded_at`, `expires_at`, and the check result fields.
  - Money is `DecimalField(10, 2)`. `compute_totals()` uses `Decimal` only. Unknown amounts stay `None` and are
    listed in `totals.unknown`; `known_total` never pretends they are zero.
- **Database constraints:**
  - `quote_version_once`, `quote_one_draft`, `quote_one_current` (one `submitted` per invitation);
  - `quote_submitted_is_frozen_shape`, `quote_end_after_start` (non-drafts);
  - `quote_amounts_not_negative`.
- **Validation (`quotes.validate`)** is deterministic and runs on every draft save (shown as `issues`) and on
  submit (`400`). It covers required fields per kind, inspection-only rules, amount ranges, per-item quantity,
  materials-amount applicability, visit-fee treatment and the time window.
- **Versions (QT-02):** `submit_draft()` turns the single draft into version *n+1* and marks the previous one
  `superseded` (with `superseded_at`). Earlier versions and their findings stay readable.
- **Expiry (QT-03):** `expires_at = min(submitted_at + QUOTE_VALIDITY_HOURS, start_at)`. An expired version is
  never ready.
- **Locking order (shared with M6):** submit takes `JobRequest` → `Invitation` → draft, all
  `SELECT … FOR UPDATE`. It checks `status == active` again **after** the locks, so a quote cannot be submitted
  after a decline or withdrawal. M6 locks the same rows in the same order (the job on send, the invitation on
  withdraw or decline), so there is no deadlock cycle.
  - PostgreSQL thread tests (`ConcurrencyTests`): five submit-vs-withdraw races never leave a version with
    `submitted_at > closed_at`, and a double submit gives exactly one version.

### Agreement-gap detection (GAP-01, GAP-02)

- **Two layers, both stored as `GapFinding` rows on the quote version:**
  1. **Rules (`quotes.rule_findings`):**
     - `timing_differs`: blocking, the customer answers; the proposed time is outside the requested window.
     - `materials_amount_unknown`: a note.
  2. **The checker (`apps/providers/agreement.py`, chosen by `AGREEMENT_CHECK_PROVIDER`):**
     - `GeminiAgreementChecker`: Interactions API, JSON schema, `store: false`, budget
       `GEMINI_AGREEMENT_MAX_TOKENS`.
     - `FixtureAgreementChecker`: labelled keyword rules for the demo's labour-vs-materials case only.
     - `UnconfiguredAgreementChecker`.
- **Minimum data:** `check_inputs()` sends:
  - the shared summary subset (description, trade, services, area, window, budget preference);
  - the approved texts of the last 40 messages;
  - the structured terms.

  All times are in one Asia/Karachi format, so equal instants are not reported as a conflict (a live false
  positive before this change). Nothing private is sent: no address, access notes, photos, audio, identity or
  phone. A test asserts this.
- **Grounding:** `verify_findings()` keeps only sources whose quoted text really appears in the input under the
  stated `kind`/`ref`, and drops findings left without sources. The UI shows those statements word for word
  (GAP-02).
- **Failure is never a pass:**
  - `run_ai_check()` runs outside the submit transaction and catches provider errors **and** unexpected
    exceptions. The result is `check_status="unavailable"` with a failure code.
  - Readiness then blocks with `automated_check_unavailable` until the check is re-run successfully, or until
    the **customer** records a manual review. That review is stored as `manual_review_by/at`, not as a pass.
- **Resolution:** `clarified` or `not_a_conflict`, with a required note. Who, which role and when are stored on
  the finding of that version. A changed price or terms means a new version, which is checked again. Old
  versions keep their findings.

### M8 hand-off

`quotes.readiness(invitation, quote=None)`, also exposed as `GET /conversations/{id}/readiness/`, returns
`{invitation_id, quote_id, version, expires_at, ready, blocking[], warnings[]}`.
- Ready requires all of these:
  - an active invitation;
  - a current, unexpired submitted version;
  - no open blocking findings;
  - a check that ran (or the customer's manual review after it could not run);
  - `worker_eligibility(...).can_take_jobs`.
- M7 stops at "Ready for customer acceptance".
- **M8 should:**
  - lock `JobRequest` → `Invitation` → `Quote` in that order;
  - call `readiness()` again inside the transaction;
  - accept exactly the `quote_id`/`version` the customer saw.

  M8 owns acceptance, booking, time reservation and arrival codes.
