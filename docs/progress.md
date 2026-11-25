# Kaam Madad — Module Progress

Requirements: [requirements.md](requirements.md) · Architecture: [architecture.md](architecture.md) · API: [api.md](api.md)

> **25 Nov 2026 — brand rename (M1 follow-up):** public name changed from *Roshan Rozgaar* to
> **Kaam Madad / کام مدد** in UI strings, page title/metadata, admin header, README and docs. Internal
> identifiers (database `roshan_rozgaar`, Compose project `roshan-rozgaar`, npm package name) are unchanged
> on purpose; see [architecture.md](architecture.md) "Naming". Frontend typecheck, tests and build re-run
> after the change.

| Module | Status |
|---|---|
| M1 Foundation | ✅ Complete (24 Nov 2026) |
| M2 Accounts, language, catalog | ✅ Complete (25 Nov 2026) |
| M3 Audio and AI adapters | ✅ Complete (25 Nov 2026) — fixture-verified; live keys not yet tested. 26 Nov: ElevenLabs read-aloud added |
| M4 Worker onboarding | ⬜ Next |
| M5 Customer and job requests | ⬜ Not started |
| M6 Recommendations and invitations | ⬜ Not started |
| M7 Communication and agreements | ⬜ Not started |
| M8 Booking and arrival | ⬜ Not started |
| M9 Completion and feedback | ⬜ Not started |
| M10 Reporting and moderation | ⬜ Not started |
| M11 Integration and delivery | ⬜ Not started |

---

## M3 follow-up (26 Nov 2026): ElevenLabs `eleven_v3` read-aloud

- `TEXT_TO_SPEECH_PROVIDER=elevenlabs` selects `ElevenLabsTextToSpeech` (`apps/providers/text_to_speech.py`);
  settings `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (required), `ELEVENLABS_MODEL_ID` (`eleven_v3`),
  `ELEVENLABS_OUTPUT_FORMAT` (`mp3_44100_128`), `ELEVENLABS_API_BASE`, `ELEVENLABS_ZERO_RETENTION`. Gemini/fixture
  speech-to-text and interpretation unchanged.
- ElevenLabs error codes mapped (`quota_exceeded` is a usage limit, not "not configured"); MP3/WAV verified by
  magic bytes; synthesised files stored and served with their real type (`.mp3` / `audio/mpeg`).
- `check_ai_providers`: `--only`, `--speak`, `--speak-language`, `--save-speech` (write the audio to listen to).
- Tests: 12 new (request shape, language hint, WAV + zero retention, error mapping, retry, configuration errors,
  API storage/playback/reuse/ownership, quota → 429, `/config/`, command save and missing key); backend **186 passed**.
- Browser, 360 px, `/voice-test` with `TEXT_TO_SPEECH_PROVIDER=elevenlabs` pointed at a **local stub** of the
  ElevenLabs endpoint (silent MP3, not the real service): typed fictional Urdu sentence → draft → confirm → read
  aloud → `201`, `audio/mpeg`, `private, no-store`, decoded by Chrome (1.56 s), no "simulated" label on read-aloud;
  stub `401 quota_exceeded` → `429 ai_provider_limit_reached`, text kept, retry offered. Logs held no text.
- **Not verified live**: no ElevenLabs key was available in this environment, so the real voice quality for Urdu
  is untested. Steps: README "Read-aloud with ElevenLabs".

## M3 Audio and AI adapters — complete (fixture-verified; live providers not yet exercised)

### Delivered

- [x] Separately configurable adapters per capability (`apps/providers`): speech-to-text, interpretation,
      text-to-speech — each with a real provider, a labelled `fixture` (demo only) and `unconfigured`
- [x] Real provider paths: **Gemini API** (`gemini-3.8-flash`, Interactions API, `store: false`) for speech-to-text
      and structured interpretation; **Azure AI Speech** (`ur-PK-UzmaNeural`, `en-IN-NeerjaNeural`) for TTS — chosen
      from current docs (Gemini API TTS does not list Urdu)
- [x] Error taxonomy: `ai_provider_not_configured` / `ai_provider_limit_reached` / `ai_provider_unavailable` /
      `ai_output_invalid`; bounded timeouts and retries; no payloads in logs
- [x] Private audio: upload (multipart), owner-only metadata and playback, server-side format/content/duration/size
      validation before storage, random file names, `private, no-store`
- [x] Transcription (original transcript kept), interpretation drafts for `worker_introduction` and
      `job_description` (validated schema, catalog mapping, negation preserved, missing/uncertain fields,
      unmatched mentions, corrections stored separately, confirmation rules), synthesis with per-owner cache
- [x] Reuse of unchanged input (transcription, interpretation, synthesis)
- [x] Live mode refuses fixture providers at startup and at runtime; `/config/` reports availability (no keys)
- [x] OCR and identity-verification boundaries (interfaces + unconfigured) and documented M4 handoff
- [x] `python manage.py check_ai_providers` for live checks
- [x] Frontend: `/voice-test` page; reusable `useRecorder` (in-browser 16 kHz WAV), `VoiceCapture`, `DraftEditor`,
      `ReadAloud`, `SimulatedBadge`, `TextArea`; API client multipart + blob support
- [x] Docs: api.md (Voice and AI), architecture.md §9, README §6 (incl. live-check steps), .env.example

### Checks run (25 Nov 2026)

| Check | Result |
|---|---|
| `python manage.py check`; `makemigrations --check` | ✅ No issues; `voice.0001` applied, nothing pending |
| Backend tests (real PostgreSQL) | ✅ **174 passed** (53 new for M3) |
| Production `check --deploy` | ✅ Only HSTS subdomain/preload warnings (M11) |
| Frontend typecheck / tests / build | ✅ No errors / **53 passed** (repeated runs) / built |
| `check_ai_providers` with fixtures | ✅ All three `[OK]`, `simulated=True` |
| `check_ai_providers` with Gemini/Azure selected and no keys | ✅ Honest `[FAIL] … ai_provider_not_configured (missing_api_key)` |
| Real browser, 360 px, **real recorder** (Chrome fake microphone playing a synthetic WAV) → real backend (fixtures) | ✅ See below |

Browser walk-through actually inspected (Urdu, then English): signed in as a worker → **recorded ~3 s through the
in-app recorder** → replay → "Write it down" (upload + server validation + transcription + interpretation) → original
transcript shows *motor rewinding* and *نہیں* → draft: name, trade, 5 years, fan installation + wiring offered,
"motor rewinding" listed as unmatched with "Said: not this" → name corrected → confirmed → read aloud (fixture tone,
"test tone, not real speech" note). From the same browser against the live server: owner playback `200` with
`private, no-store`; 10 MB+ upload `413 audio_too_large`; text file named `.wav` `415 audio_unsupported`; **another
account `404`**. Second run with `TEXT_TO_SPEECH_PROVIDER=unconfigured`: typed-input path → corrected experience
(7) → confirmed → read aloud fails with "not set up on the server", confirmed text (with the correction) stays
visible, retry offered; switching to English re-translates everything. No horizontal overflow at 360 px.

Automated coverage also includes: Gemini request shape (`/interactions`, `x-goog-api-key`, `Api-Revision`,
`store: false`, base64 audio part, schema), both response shapes, 429/401/503/timeout/400 mapping, retry-then-success,
invalid outputs; Azure SSML escaping, headers, voice choice, error mapping; invalid model output (wrong types, missing
keys, non-object) → `ai_output_invalid` with nothing stored; invented names, unknown catalog codes, out-of-range
years and conflicting services handled; prompt-injection text cannot change the account; corrections validated and
kept separate; confirmation rules; other accounts cannot read/patch/confirm drafts; per-user upload rate limit;
transcripts absent from logs.

### Issues found and fixed during validation

- **Error messages did not follow a language switch** (found in the browser): components stored translated strings.
  Now errors/codes are stored and translated at render — fixed on the voice page and on the M2 login, signup and
  phone pages; regression test added.
- Duplicate accessible labels on draft fields (screen readers heard each label twice) — removed.
- Provider error wording assumed the input step ("type instead") also on read-aloud — made context-neutral.
- `check_ai_providers` crashed instead of reporting when a selected provider had no key — fixed and tested.

### Known limitations / not verified

- **Live providers not exercised**: no Gemini or Azure credentials were available. Real adapters are tested only
  against mocked HTTP in the documented shapes. The raw Gemini Interactions **response** JSON is not shown in the
  docs; the adapter accepts the documented `output_text` and `steps[].model_output` forms and otherwise fails
  closed. Run the README "Live check" before relying on real providers.
- **No real Urdu speech recording was used**: the fixture transcript is fixed sample text; the browser test
  recorded a synthetic tone. Speech recognition quality on real phones is untested (requirement §12 evaluation set
  is still to do).
- Recording needs HTTPS or localhost; phones on the dev server over LAN http fall back to upload/typing.
- Fixture interpretation is keyword rules, not language understanding — demo/testing only.
- Synthesis is unbounded in count per user except by the rate limit; old private files are not yet purged
  (retention policy: M10). No staff access to audio yet (needs audit, M10).
- Files from rejected DB transactions in tests remain in the temporary test media folder only.

### Environment needed for live capability

`GEMINI_API_KEY` (+ `SPEECH_TO_TEXT_PROVIDER=gemini`, `INTERPRETATION_PROVIDER=gemini`) and `AZURE_SPEECH_KEY`,
`AZURE_SPEECH_REGION` (+ `TEXT_TO_SPEECH_PROVIDER=azure`). Nothing else.

### Next module

**M4 — Worker onboarding**: voice introduction draft (uses M3 APIs), private CNIC/OCR, verification adapter and admin
queue, the three speciality questions, location/coverage, eligibility and profile confirmation.

---

## M2 Accounts, language, catalog — complete

### Delivered

- [x] `auth/csrf`, `auth/signup`, `auth/login`, `auth/logout`, `auth/me`, `auth/me/language` (contracts in [api.md](api.md))
- [x] Signup with normalised phone, Django password validation/hashing, worker/customer role, preferred language;
      strict fields (no staff/verification/restriction fields, no role changes); demo accounts flagged in demo mode
- [x] CSRF enforced on all mutations including anonymous signup/login; 401 vs 403 distinction; session rotation
- [x] Rate limits (login per IP + per phone, signup per IP, phone codes per IP) in a PostgreSQL cache table
- [x] Suspended (`is_active=False`) users lose access, including existing sessions
- [x] Server-side role permissions (`IsWorker`, `IsCustomer`, `IsMarketplaceUser`)
- [x] Deployment mode (`live`/`demo`) and phone-verification provider (`demo`/`unconfigured`); live mode refuses the
      demo provider at startup
- [x] Phone confirmation: provider boundary, labelled demo sender, honest unconfigured sender, digest-only challenges,
      10-min expiry, 5 attempts, 60 s cooldown, 5/hour, supersede/consume, status separate from method
- [x] Catalog models, admin, public read APIs with filters/pagination, speciality-questions endpoint + rules,
      idempotent `seed_catalog`
- [x] Frontend: start (language + role), signup, login, phone confirmation (demo flow), worker/customer/staff homes,
      catalog preview, auth bootstrap, guards, session-expired flow, logout, persistent sessions, demo banner
- [x] Urdu/English switch (device + account), account preference applied after login; translated validation,
      loading, empty, success and error states (server codes → translation keys)
- [x] Reusable components: Button/ButtonLink, TextField/PasswordField/FieldErrors, IconTileGroup, LanguageSwitch,
      StatusBadge, Alert, PageLoader, AudioButton
- [x] Docs: api.md (new), architecture.md §8, README usage/integration table, .env.example

### Checks run (25 Nov 2026, same environment as M1)

| Check | Command | Result |
|---|---|---|
| Django system check | `python manage.py check` | ✅ No issues |
| Migrations | `migrate`; `makemigrations --check --dry-run` | ✅ accounts.0002, catalog.0001, core.0001 applied; no pending changes |
| Seed idempotency (real DB) | `seed_catalog` twice | ✅ Run 1: 3/23/2/19/3 created; run 2: 0 created, 0 updated |
| Backend tests (real PostgreSQL) | `python manage.py test --settings=config.settings.test` | ✅ **121 passed** (~30 s) |
| Production settings | `check --deploy` with live+unconfigured and demo+demo | ✅ Only HSTS subdomain/preload warnings (M11 decision); live + demo provider refused at startup |
| Frontend typecheck | `npm run typecheck` | ✅ No errors |
| Frontend tests | `npm test` | ✅ **45 passed** (3 consecutive runs) |
| Frontend build | `npm run build` | ✅ JS 123 KB gzip |
| Real browser end-to-end, 360 px mobile emulation, real Django + PostgreSQL | scripted walk-through (Chrome DevTools protocol) | ✅ See below |

Backend tests cover: signup validation, phone normalisation/uniqueness, password rules, privilege-escalation
attempts, role restrictions, login/logout/session persistence/rotation, inactive and mid-session-deactivated users,
real CSRF enforcement (login, signup, stale token after rotation, logout), throttling (per phone/per IP), language
persistence across sessions, role permissions, demo OTP (issue, digest storage, no logging, Urdu digits, wrong
codes, attempt limit, expiry, cooldown, supersede, hourly limit, phone binding), unconfigured provider, runtime and
startup production guards, catalog API filters/search (Urdu and English)/pagination/ordering/inactive hiding,
speciality questions and rules, seed idempotency/staff-record preservation/dry run, and the existing M1 tests.

Browser walk-through actually inspected (screenshots viewed, 360 px, both languages): Urdu start → worker signup →
phone confirmation with demo code → confirmed ("Demo confirmation (not real verification)") → Urdu worker home →
switch to English → **full reload** (session and account language persisted; `/auth/me/` returned
`preferred_language: en`) → role guard (`/customer` → `/worker`) → logout → landing → protected page asks to log
in → wrong password (translated error) → login → worker home → catalog. No horizontal overflow on any screen
(`scrollWidth == 360`). The masked phone number renders in correct LTR order inside Urdu text.

### Issues found and fixed during validation

- **Signup/login redirect race** (found in the browser): the guest-only guard redirected newly signed-in users home
  before the form could navigate, skipping phone confirmation and losing `?next=`. The guard now only redirects
  users who were already signed in on arrival. Regression tests added.
- **Logout redirect race**: logging out from a protected page went to login instead of the landing page. Fixed with
  an explicit `loggedOut` state. Regression test added.
- **Wrong-direction frame**: `<html dir>` was set after paint, so English text could briefly render RTL (caught by an
  intermittent test). Fixed with a layout effect.
- **Label/number spacing** collapsed at the RTL/LTR boundary; fixed with flex gaps.
- M1 test expectation changed deliberately: anonymous API access now returns 401 (was 403).

### Known limitations

- **No real SMS provider.** Demo codes are simulated and labelled; `unconfigured` reports unavailability honestly. A
  real pilot needs a provider implementation (boundary in architecture.md §8) and credentials.
- **No real phones tested.** Inspection used desktop Chrome with 360 px mobile emulation only.
- Password policy uses Django's defaults (8+ characters, not common, not only digits); suitability for low-literacy
  users needs user testing.
- Signup reveals whether a phone number is registered (`phone_taken`); rate limiting mitigates enumeration.
- Area centre coordinates are intentionally empty until verified (needed for approximate distance in M6).
- `AudioButton` exists but no audio assets are wired in yet (M3); it renders nothing without audio.
- Transient environment observation: twice a new PostgreSQL connection through Docker Desktop exceeded the 3 s
  connect timeout (a later sample of 60 connections: median 32 ms, max 151 ms). The UI showed an honest error and
  a retry.
- The browser walk-through created a few fictional demo accounts in the local development database.

### Environment needed

No provider keys. Run `migrate` then `seed_catalog`. Production needs `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
and either `APP_DEPLOYMENT_MODE=demo` (separate demo deployment) or a live deployment without simulated phone codes.

### Next module

**M3 — Audio and AI adapters**: recording/upload, transcription, structured interpretation, TTS, private media,
provider modes, schema validation, failure handling.

---

## M1 Foundation — complete

### Delivered

- [x] New repository structure, `.gitignore` (secrets, private media, builds), `.env.example` files
- [x] Docker Compose PostgreSQL 18 (localhost-only binding, host port 5434, health check)
- [x] Django 6.1 / DRF 3.18 project with `development` / `production` / `test` settings
- [x] Custom user model before first migration: UUID id, normalised unique Pakistani mobile login, worker/customer
      role (no staff authority), preferred language (Urdu default), active + demo flags, Django staff/superuser
      permissions; DB check constraints for phone format, role and language
- [x] Shared API error envelope (`code`, `message`, `request_id`, optional `fields`/`details`), DRF exception
      handler, API-aware Django 400/403/404/500 handlers, JSON 404 for unknown `/api/` paths
- [x] Request IDs on every response, error body and log line
- [x] `GET /api/v1/health/live/` and `GET /api/v1/health/ready/` (503 envelope when the DB is unreachable)
- [x] Django Admin: phone-aware user forms, masked list, filters, normalised search
- [x] React/TypeScript/Vite/Tailwind frontend: router, mobile-first shell, Urdu-first i18n structure with RTL,
      bundled Nastaliq font, API client, landing screen with live readiness states and retry
- [x] Same-origin production serving: WhiteNoise + SPA catch-all
- [x] README with Windows PowerShell and Linux instructions; requirements/architecture/progress docs

### Checks run (24 Nov 2026, Windows 11, Python 3.14.0, Node 24.12.0, PostgreSQL 18.7 in Docker)

| Check | Command | Result |
|---|---|---|
| Django system check | `python manage.py check` | ✅ No issues |
| Migrations created/applied on PostgreSQL | `python manage.py migrate`; `makemigrations --check --dry-run` | ✅ All applied; no pending changes |
| DB constraints present | `psql \d accounts_user` | ✅ UUID PK, unique phone, 3 check constraints |
| Backend tests (real PostgreSQL test DB) | `python manage.py test --settings=config.settings.test` | ✅ **65 passed** (10.6 s) |
| Frontend typecheck | `npm run typecheck` | ✅ No errors (TypeScript 7.0.2) |
| Frontend tests | `npm test` | ✅ **18 passed** |
| Frontend production build | `npm run build` | ✅ Built (JS 104 KB gzip; fonts separate) |
| Dev proxy reaches backend | `curl http://localhost:5173/api/v1/health/ready/` | ✅ 200, `X-Request-ID` preserved |
| Real browser, 360 px mobile emulation (Chrome DevTools protocol) | Urdu + English, DB up | ✅ Status "ready", `lang/dir` correct, font loaded, no horizontal overflow |
| Readiness failure, real (DB container stopped) | curl + browser | ✅ live 200; ready 503 `service_not_ready` in 3.3 s; UI shows "database unavailable" + retry (52 px) |
| Backend down, real (Django stopped) | curl + browser | ✅ Vite returns 502 text; UI shows "could not reach the server" + retry |
| Production settings, same origin | `collectstatic`, `check --deploy`, runserver on :8001 | ✅ SPA `no-cache`; hashed assets + admin static `immutable`; API + admin on same port; cookies `Secure; SameSite=Lax` |
| Production fail-fast | subprocess tests | ✅ Refuses missing/insecure secret key and missing allowed hosts |

Test coverage includes: phone normalisation (incl. Urdu digits, bidi marks, landlines rejected), password hashing,
uniqueness across formats, DB constraints bypassing Python, staff flags vs marketplace role, admin access/forms/search
and masking, health (zero DB queries on liveness, real unreachable-DB connection, no internal details leaked),
error envelope (validation flattening, parse errors, 409 details, default deny, generic 500 without leaks),
SPA serving/caching, request-ID logging; frontend client error classification (envelope, offline, timeout,
gateway 5xx, cancellation), status card states and retry, i18n RTL/LTR + key parity, routing.

### Issue found and fixed during validation

`POSTGRES_HOST=localhost` added **~5 s to every new database connection** on Windows + Docker Desktop (IPv6 `::1`
attempt hangs until `connect_timeout`), and made a failed readiness check take 10 s — hitting the frontend's
10 s timeout so the UI said "timeout" instead of "database unavailable". Default changed to `127.0.0.1` and
`POSTGRES_CONNECT_TIMEOUT` to 3 s. Effect measured: connect 5.11 s → 0.05 s; readiness failure 10.2 s → 3.3 s;
backend test suite 51 s → 10.6 s.

### Known limitations / not verified

- **No real phones tested yet.** Rendering was verified in desktop Chrome with 360 px mobile emulation only;
  NFR-01's two physical phone/browser combinations remain for later modules (M2 shell, M11 validation).
- **Production deployment not done.** Same-origin production settings were verified locally over HTTP with
  `runserver`; the WSGI server, HTTPS, Content-Security-Policy, and HSTS subdomain/preload decisions are M11.
- The existing local PostgreSQL 18 service on port 5432 was **not** used (credentials unknown); the
  "existing instance" path is documented but was verified only via the Compose database.
- Tested on Windows only; Linux commands are documented but were not executed in this environment.
- Language switch UI, auth endpoints, CSRF bootstrap, rate limiting, demo/production mode flag: M2 (by design).
- `createsuperuser` accepts phone input up to 13 characters (type `03001234567`, not `+92 300 1234567`);
  the admin form accepts any format.

### Environment needed

None beyond `.env` database settings. No provider keys are used in M1.

### Next module

**M2 — Accounts, language, catalog**: session/CSRF auth endpoints, roles, demo-labelled phone adapter,
Urdu/English shell with persistent switch and reusable audio/icon controls, seeded trade/service/area catalog.
