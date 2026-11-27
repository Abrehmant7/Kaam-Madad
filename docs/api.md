# Kaam Madad — API Contracts

All endpoints are under `/api/v1/`, return JSON, and are served from the same origin as the web app.
Implemented through **M9**. Planned endpoint families for later modules are listed in
[requirements.md §10](requirements.md#10-api-contracts-and-screen-inventory) and are **not** implemented.

## Conventions

**Errors** always use one envelope (stable `code` → client translation; `message` is an English fallback):

```json
{"error": {"code": "validation_error", "message": "…", "request_id": "uuid",
           "fields": {"phone_number": [{"code": "phone_taken", "message": "…"}]},
           "details": {"retry_after_seconds": 42}}}
```

`fields` appears only for validation errors (nested paths are dotted, e.g. `items.1.amount`; errors not tied to
a field use `non_field_errors`). `details` holds optional non-sensitive context. Every response has an
`X-Request-ID` header equal to `request_id`.

| Status | Meaning | Typical codes |
|---|---|---|
| 400 | Invalid input or rejected action | `validation_error`, `invalid_credentials`, `code_incorrect`, `code_expired`, `no_active_code`, `parse_error` |
| 401 | No valid session (log in) — header `WWW-Authenticate: Session` | `not_authenticated` |
| 403 | Signed in / identified but not allowed | `permission_denied`, `csrf_failed`, `account_inactive`, `worker_role_required`, `customer_role_required`, `marketplace_role_required`, `worker_only`, `customer_only`, `not_allowed_for_role` |
| 404 | Unknown resource or `/api/` path | `not_found` |
| 409 | Conflicts with current state | `already_authenticated`, `phone_already_confirmed`, `invitation_already_active`, `invitation_closed`, `conversation_closed`, `no_quote_draft`, `quote_not_current`, `check_not_needed`, `job_already_booked`, `invitation_booked`, `quote_expired`, `quote_not_ready`, `invitation_not_active`, `schedule_conflict`, `worker_not_eligible`, `idempotency_key_reused`, `booking_state_conflict`, `cancel_not_allowed`, `worker_has_job_in_progress`, `change_pending`, `change_not_pending`, `time_change_not_allowed` |
| 429 | Rate limited (`Retry-After` header; `details.retry_after_seconds`) | `throttled`, `resend_too_soon`, `send_limit_reached`, `too_many_attempts` |
| 500 / 503 | Server error / not ready or provider unavailable | `server_error`, `service_not_ready`, `phone_verification_unavailable` |

**Authentication** uses Django sessions (HttpOnly `sessionid` cookie). **CSRF**: every `POST/PUT/PATCH/DELETE` —
including anonymous signup and login — must send the `csrftoken` cookie value in the `X-CSRFToken` header. Get
the cookie from `GET /auth/csrf/`. Login rotates both the session key and the CSRF token. Unknown request fields
are rejected with field code `unexpected_field`.

**Rate limits** (`settings.API_THROTTLE_RATES`, stored in the database cache): login 60/hour per IP and 10/hour
per phone number; signup 30/hour per IP; phone-code issue/verify 60/hour per IP. Phone-code policy is separate
(below).

**Pagination** (list endpoints): `?page=N&page_size=M` (default 50, max 200) →
`{"count", "next", "previous", "results"}`.

## Foundation (M1)

| Method & path | Auth | Response |
|---|---|---|
| `GET /health/live/` | public | `200 {"status":"ok"}` (no database access) |
| `GET /health/ready/` | public | `200 {"status":"ok","checks":{"database":"ok"}}` or `503 service_not_ready` with `details.checks` |

## Client configuration (M2)

`GET /config/` — public, server-controlled, non-secret:

```json
{"deployment_mode": "demo",
 "phone_verification": {"provider": "demo", "available": true, "simulated": true},
 "languages": ["ur", "en"], "default_language": "ur"}
```

## Accounts (M2)

**User object** (phone number always masked):

```json
{"id": "uuid", "phone_number_masked": "+92 3** ***4567", "role": "worker" | "customer" | null,
 "preferred_language": "ur" | "en", "is_demo": true, "is_staff": false,
 "phone_confirmation": {"status": "unconfirmed" | "confirmed", "method": null | "demo" | "sms", "confirmed_at": null | "ISO-8601"},
 "date_joined": "ISO-8601"}
```

| Method & path | Auth | Request | Success | Errors |
|---|---|---|---|---|
| `GET /auth/csrf/` | public | — | `200 {"csrf_token"}` + `csrftoken` cookie | — |
| `GET /auth/me/` | public | — | `200 {"authenticated": bool, "user": User \| null}` (never 401) | — |
| `POST /auth/signup/` | anonymous + CSRF | `phone_number`, `password`, `password_confirm`, `role` (`worker`/`customer`), `preferred_language` (`ur`/`en`, default `ur`) | `201 {"authenticated": true, "user"}`; session started | 400 fields: `invalid_pk_mobile`, `phone_taken`, `password_mismatch`, `password_too_short`, `password_too_common`, `password_entirely_numeric`, `password_too_similar`, `invalid_choice`, `required`, `unexpected_field`; 409 `already_authenticated`; 429 |
| `POST /auth/login/` | CSRF | `phone_number` (any format), `password` | `200 {"authenticated": true, "user"}`; session + CSRF rotated | 400 `invalid_credentials` (same for unknown phone and wrong password) or field `invalid_pk_mobile`; 403 `account_inactive` (only with the correct password); 429 |
| `POST /auth/logout/` | CSRF | — | `204` (idempotent) | 403 `csrf_failed` |
| `PATCH /auth/me/language/` | signed in + CSRF | `{"preferred_language": "ur" \| "en"}` only | `200 {"authenticated": true, "user"}` | 400 `invalid_choice`, `unexpected_field` (e.g. `role`); 401 |

Signup never accepts staff flags, verification state, restriction state, or any other user field. Accounts
created in a demo deployment get `is_demo: true`. There is no endpoint that changes `role`.

## Phone confirmation (M2)

Confirms control of the phone number only — **not** legal identity or trade competence.

| Method & path | Auth | Success | Errors |
|---|---|---|---|
| `GET /auth/phone-confirmation/` | signed in | `200` state (below) | 401 |
| `POST /auth/phone-confirmation/` | signed in + CSRF | `201` state, plus `demo` **only** in demo deployments | 409 `phone_already_confirmed`; 429 `resend_too_soon` / `send_limit_reached` (`details.retry_after_seconds`); 503 `phone_verification_unavailable` (no challenge created) |
| `POST /auth/phone-confirmation/verify/` | signed in + CSRF | `200 {"authenticated": true, "user"}` (status `confirmed`, method `demo` or `sms`) | 400 field `invalid_code_format`; 400 `code_incorrect` (`details.attempts_remaining`), `code_expired`, `no_active_code`; 429 `too_many_attempts` |

State:

```json
{"status": "unconfirmed", "method": null, "confirmed_at": null,
 "provider": {"provider": "demo", "available": true, "simulated": true},
 "active_code": {"id": "uuid", "method": "demo", "expires_at": "ISO-8601", "expires_in_seconds": 600,
                 "attempts_remaining": 5, "resend_available_in_seconds": 60},
 "demo": {"code": "482913", "notice": "DEMO ONLY: no SMS was sent. …"}}
```

Policy (`settings.PHONE_VERIFICATION_POLICY`): 6-digit code, valid **10 minutes**, **5** wrong attempts, then the
code is invalidated; **60 s** between codes; at most **5** codes per account per rolling hour. A new code
supersedes any open one; consumed codes cannot be reused; a code is bound to the account, the phone number
at issue time, and the purpose. Only an HMAC-SHA256 digest is stored; codes are never logged and the demo
code is returned only once, in the issuing response. Urdu/Arabic-Indic digits are accepted.

## Catalog (M2)

Public, read-only, active entries only. Labels are bilingual: `"labels": {"ur": "…", "en": "…"}`. Ordering is
deterministic (`sort_order`, then `code`). `icon` is a controlled identifier (`backend/apps/catalog/icons.py`).

| Method & path | Filters | Item fields |
|---|---|---|
| `GET /catalog/trades/` | `search` | `code`, `labels`, `icon`, `sort_order`, `service_count` |
| `GET /catalog/service-tags/` | `trade` (comma-separated codes), `search` (Urdu or English) | `code`, `trade` (code), `labels`, `icon`, `sort_order` |
| `GET /catalog/cities/` | — | `code`, `labels`, `sort_order` |
| `GET /catalog/areas/` | `city` (comma-separated), `kind` (`sector`/`locality`), `search` | `code`, `city` (object), `labels`, `kind`, `centre` (`{latitude, longitude, approximate: true}` or `null`), `sort_order` |
| `GET /catalog/trades/{code}/speciality-questions/` | — | see below (not paginated; unknown/inactive trade → 404) |

Speciality questions (the three later worker questions, WK-02):

```json
{"trade": {…Trade},
 "questions": [
   {"code": "services_offered", "prompt": {"ur": "آپ الیکٹریشن کی کون سی خدمات فراہم کرتے ہیں؟", "en": "Which Electrician services do you offer?"},
    "help": {…}, "selection": {"multiple": true, "min": 1, "max": null, "choices_from": "trade_services"}},
   {"code": "primary_specialities", …, "selection": {"multiple": true, "min": 1, "max": 3, "choices_from": "services_offered"}},
   {"code": "services_not_offered", …, "selection": {"multiple": true, "min": 0, "max": null, "choices_from": "trade_services"}}],
 "choices": [{…ServiceTag of this trade}],
 "rules": [{"type": "disjoint", "questions": ["services_offered", "services_not_offered"], "message_code": "offered_and_excluded_overlap"},
           {"type": "subset", "question": "primary_specialities", "of": "services_offered", "message_code": "primary_not_offered"}]}
```

Answers are validated server-side by `apps.catalog.speciality.validate_speciality_answers` (used by M4).

## Voice and AI (M3)

All endpoints require a signed-in active user and only touch that user's own records — another
account's IDs return **404** (existence is not revealed). Mutations need CSRF like every other mutation.
Provider failures use distinct codes:

| Code | Status | Meaning | `details` |
|---|---|---|---|
| `ai_provider_not_configured` | 503 | No provider selected, key missing (`reason: missing_api_key`), or key rejected (`credentials_rejected`) | `capability`, `reason` |
| `ai_provider_limit_reached` | 429 | The provider's usage/rate limit | `capability`, `retry_after_seconds` (if sent) |
| `ai_provider_unavailable` | 502 | Timeout, network or provider error after bounded retries | `capability`, `reason` |
| `ai_output_invalid` | 502 | Provider answered but the result failed schema validation (nothing stored) | `capability`, `reason` |

`capability` is `speech_to_text`, `interpretation` or `text_to_speech`. `GET /config/` additionally returns
`"ai": {"speech_to_text"|"interpretation"|"text_to_speech": {"provider", "available", "simulated"}}` and
`"voice_limits": {"max_audio_bytes", "max_audio_seconds", "max_synthesis_chars"}` — never keys.

Rate limits: `audio_upload_user` 60/hour, `ai_request_user` 120/hour (transcribe, interpret, synthesise), per user.

### Private audio

| Method & path | Request | Success | Errors |
|---|---|---|---|
| `POST /audio/clips/` | multipart: `file`, `purpose` (`worker_introduction` / `job_description`), `source` (`recording` / `upload`) | `201` clip | `413 audio_too_large` (> 10 MB), `415 audio_unsupported`, `400 audio_invalid`, `400 audio_too_long` (> 60 s), `400 audio_too_short` (< 0.3 s), `429` |
| `GET /audio/clips/{id}/` | — | `200` clip | `404` |
| `GET /audio/clips/{id}/content/` | — | `200` audio bytes, `Cache-Control: private, no-store` | `401`, `404` |

Clip: `{"id", "purpose", "source", "mime_type", "size_bytes", "duration_seconds", "created_at", "content_url"}`.
Format and duration are verified **from the file bytes on the server** before storage (client name/type
ignored). Accepted: WAV (the in-app recorder: 16 kHz mono PCM), MP3, M4A/MP4 (AAC), AAC (ADTS), OGG
(Opus — incl. WhatsApp voice notes — or Vorbis), FLAC. WebM is rejected (duration not verifiable server-side).

### Transcription

`POST /audio/transcribe/` `{"clip_id", "language": "ur" | "en" | "auto"}` → `200`:
`{"id", "clip_id", "text", "language" ("ur"|"en"|"mixed"|"unknown"), "language_hint", "no_speech", "provider",
"model", "simulated", "reused", "created_at"}`. `text` is the original transcript in the spoken language (Urdu
script, English trade terms as spoken) and is never edited. The same clip + provider + model + hint returns
the stored result (`reused: true`) without calling the provider again.

### Interpretation drafts

| Method & path | Request | Success | Errors |
|---|---|---|---|
| `POST /interpretations/` | `{"kind", "language", "transcription_id"}` **or** `{"kind", "language", "text"}` (≤ 4000 chars) | `201` interpretation | `400 transcription_or_text_required`, `400 no_speech`, `404`, provider codes |
| `GET /interpretations/{id}/` | — | `200` | `404` |
| `PATCH /interpretations/{id}/` | `{"fields": {...}}` — corrections only | `200` | `400` field codes `unexpected_field`, `unknown_trade`, `unknown_area`, `unknown_service`, `invalid`, `max_length`; `409 draft_already_confirmed` |
| `POST /interpretations/{id}/confirm/` | — | `200` (`confirmed` set) | `400` `fields.<name>`: `required`, `offered_and_excluded_overlap`; `409 draft_already_confirmed` |

Interpretation:

```json
{"id": "uuid", "kind": "worker_introduction", "language": "mixed",
 "source": {"text": "<original transcript or typed text>", "transcription_id": "uuid|null"},
 "draft": {"fields": {...}, "missing": ["name"], "uncertain": ["preferred_time_text"],
           "unmatched_mentions": [{"phrase": "motor rewinding", "negated": true}], "heard": {"area": "<as said>"}},
 "corrections": {"name": "..."},
 "effective_fields": {"...draft fields overlaid with corrections..."},
 "confirmed": null | {"fields": {...}, "confirmed_at": "ISO-8601"},
 "provider": "gemini", "model": "gemini-3.8-flash", "simulated": false, "reused": false, "created_at": "..."}
```

Fields — **worker_introduction**: `name` (≤ 80), `trade` (trade code), `years_experience` (0–70, self-reported),
`services_offered`, `services_not_offered` (service codes). Required to confirm: `name`, `trade`.
**job_description**: `description` (faithful Urdu draft ≤ 1000), `trade`, `services`, `services_excluded`, `area`
(area code), `preferred_time_text` (as said, not converted to a date), `budget_pkr` (customer's preference, optional).
Required to confirm: `description`, `trade`, `area`, `preferred_time_text`.

Guarantees: codes are always active catalog entries (anything else is left unset and reported as unmatched or
uncertain); negated mentions are kept as negated ("not offered" / "not wanted"), never flipped; a service said both
ways is removed from both and marked uncertain; a name that does not appear in the source text is dropped;
`draft` and `source.text` never change — corrections live in `corrections`. Confirming stores the draft only: it
does not publish a profile or create a job. Identical text (same kind, language, provider, model and catalog) reuses
the previous provider result in a new record (`reused: true`).

### Speech synthesis

`POST /audio/synthesise/` `{"text" (≤ 1500), "language": "ur" | "en"}` → `201`
`{"id", "language", "voice", "provider", "simulated", "mime_type", "size_bytes", "content_url", "reused"}`.
`mime_type` is `audio/wav` (fixture, Azure, ElevenLabs `wav_*`) or `audio/mpeg` (ElevenLabs default `mp3_44100_128`);
`provider` is `fixture`, `azure` or `elevenlabs`; for ElevenLabs `voice` is `<model>/<voice id>`.
`GET /audio/syntheses/{id}/content/` → owner-only audio of that type, `private, no-store`. Cached per owner only (same text,
language, provider and voice → `reused: true`); never in a shared cache.

## Workers and identity (M4)

All endpoints need a signed-in **worker** (`403 worker_role_required` otherwise). Each worker sees only their
own records; another account's IDs return `404`.

### Onboarding and dashboard

`GET /workers/me/` → the dashboard payload (the profile is created on first use):

```json
{"profile": {"trade": "electrician", "services_offered": ["elec_fan_install", "elec_wiring_repair"],
             "primary_specialities": ["elec_fan_install"], "services_not_offered": ["elec_ups_inverter"],
             "city": "islamabad", "service_areas": ["isb-g-10", "isb-g-9"], "accepting_requests": true,
             "updated_at": "…"},
 "onboarding": {"complete": true, "next_step": null,
                "steps": {"work": {"complete": true, "issues": []}, "areas": {"complete": true, "issues": []}}},
 "identity": {"status": "not_started", "case_id": null, "method": null, "masked_cnic": null, "simulated": false,
              "counts_here": false, "decided_at": null, "updated_at": null},
 "eligibility": {"can_take_jobs": false, "receives_requests": false, "reasons": ["identity_not_started"]},
 "identity_provider": {"provider": "demo_registry", "available": true, "simulated": true}}
```

- **`next_step`** is `"work"`, `"areas"` or `null`. Completion is always recomputed on the server from the stored
  choices and the live catalog; it is never stored as a flag.
- **`identity.status`** is one of: `not_started`, `in_progress`, `no_match`, `demo_approved`,
  `provider_verified`, `manually_reviewed`, `rejected`, `expired`, `suspended`.
- **`counts_here`** says whether that status is accepted in this deployment.
- **`eligibility.reasons`** can contain: `account_inactive`, `profile_incomplete`, `identity_not_started`,
  `identity_not_verified`, `identity_no_match`, `demo_approval_not_accepted_here`, `identity_rejected`,
  `identity_expired`, `identity_suspended`, `not_accepting_requests`.

Screen 2: `PUT /workers/me/work/`. The request body is
`{"trade", "services_offered": [], "primary_specialities": [], "services_not_offered": []}`, and the response
is the dashboard payload. It is validated with the catalog rules (`apps.catalog.speciality`) and the question
limits; field error codes:

- `trade`: `required`, `unknown_trade`.
- `services_offered` (at least 1): `too_few`, `unknown_service` (inactive, or another trade's service).
- `primary_specialities` (exactly 1): `too_few`, `too_many`, `primary_not_offered`.
- `services_not_offered`: `offered_and_excluded_overlap`.

Screen 3: `PUT /workers/me/areas/` `{"city", "service_areas": []}` → the dashboard payload. Field error codes:
`city` → `required`, `unknown_city`; `service_areas` → `too_few`, `unknown_area`, `area_not_in_city`.

`PATCH /workers/me/preferences/` `{"accepting_requests": bool}` → the dashboard payload. This is the worker's own
choice and is separate from completion and identity.

### Identity verification

Scanning, review and the registry check are separate steps. OCR never approves anything.

1. **Start:** `POST /identity/cases/` `{"consent": true}` → `201 {"case": Case, "provider": {…}}`.
   - Without consent: `400`, field `consent` → `consent_required`.
   - A new attempt supersedes an unfinished one.
   - `409 verification_already_complete` once accepted here.
   - `409 verification_not_editable` when suspended.
2. **Current attempt:** `GET /identity/cases/` → `{"case": Case | null, "provider": {…}}`.
3. **Scan:** `POST /identity/cases/{id}/scan/`, multipart field `image` (a JPEG/PNG/WebP photo of the card front) →
   `{"case": Case}`. The image is validated and then read by **Tesseract on the server**; it is **not stored**.
   - Image errors: `413 image_too_large` (> 5 MB), `415 image_unsupported` (wrong or corrupt type),
     `400 image_dimensions` (under 400 × 250 px or over 40 MP).
   - OCR errors carry `details.capability: "cnic_ocr"`, a `details.reason` and the updated `details.case`:
     - `503 ai_provider_not_configured`, with reason `tesseract_not_found`, `tesseract_not_runnable` or
       `tesseract_language_missing`.
     - `502 ai_provider_unavailable`, with reason `ocr_timeout` or `ocr_engine_error`.
4. **Submit:** `POST /identity/cases/{id}/submit/` `{"name", "cnic_number"}` → `{"case": Case, "eligibility": {…}}`.
   - These are the details the worker confirmed or corrected; the number is accepted with or without dashes.
   - Field codes: `invalid_name`, `invalid_cnic`.
   - `409 verification_scan_required` until a scan has been processed (read, partial or unreadable).
   - `503 identity_provider_not_configured` when no registry is available (live mode); nothing is approved.

```json
{"id": "…", "status": "demo_approved", "case_id": "…", "method": "demo_registry", "masked_cnic": "*****-*****67-1",
 "simulated": true, "counts_here": true, "decided_at": "…", "updated_at": "…",
 "consent": {"given_at": "…", "version": "2026-11-27"},
 "scan": {"count": 1, "scanned_at": "…", "width": 856, "height": 546},
 "ocr": {"status": "read", "provider": "tesseract", "engine": "tesseract v5.4.0…", "rotation": 0, "failure": null,
         "simulated": false, "name": null, "cnic_number": null},
 "review": {"submitted_at": "…", "name_corrected": false, "number_corrected": false},
 "registry": {"outcome": "match", "provider": "demo_registry", "simulated": true, "reference": "DEMO-REG-0001",
              "checked_at": "…", "attempts": 1, "demo_address": "House 12, Street 4, Demo Town, Islamabad"}}
```

- **`ocr.status`** is `not_run`, `read` (name and number), `partial` (one of them), `unreadable` or `failed`.
- **`ocr.name` and `ocr.cnic_number`** are the ORIGINAL scan result, returned to the owner for review until the
  attempt is approved. The full number never appears in any other payload.
- **`review.*_corrected`** records whether the submitted values differ from the scan.
- **`registry.outcome`** is `not_checked`, `match`, `name_mismatch` (the number exists but the name differs; the
  recorded name is never revealed) or `no_record`.
- **Matching:** names are compared without regard to case or spacing, and numbers without regard to dashes.
- **`demo_address`** is fictional. It is shown labelled "Demo address" and is never a service area.

### Fixed instructions

`GET /instructions/{key}/audio/?language=ur|en` is public, because screen 1 is before login. It returns speech
for one fixed instruction: `signup_password`, `onboarding_work`, `onboarding_areas` or `identity_consent`.
- **Only fixed text:** the server owns the text, so nothing the user typed can reach speech synthesis.
- **Cached:** each key, language and voice is synthesised once.
- **Header:** `X-Audio-Simulated: 1` marks the fixture tone.
- **Errors:** `404` for an unknown key; provider errors as in Voice and AI.

`GET /config/` also returns `ai.cnic_ocr` (`{"provider": "tesseract", "available", "simulated": false}`) and
`identity_verification`.

## Job requests (M5)

**Access:**
- Every endpoint needs a signed-in **customer**. Workers get `403 customer_role_required`.
- Only the customer's own requests are visible; another customer's request or photo IDs return `404`.
- Ownership of attached audio, transcriptions and interpretations comes from the session.

**Statuses:** `draft` is saved, resumable and editable. `confirmed` is validated and read-only in M5.
Confirming **saves** the request; it does not invite a worker or reserve a time (that is M6 and later).

### Create and list

- `POST /jobs/` creates a draft → `201 Job`.
  - Body: `{"source_kind": "text", "original_text": "…", "source_language": "ur"|"en"}`
    or `{"source_kind": "voice", "audio_clip_id": "<own clip, purpose job_description>"}`.
  - Errors: `original_text`/`audio_clip_id` → `required`; another customer's clip → `audio_clip_id: not_found`.
- `GET /jobs/?status=draft|confirmed&page=&page_size=` → paginated
  `{"count", "next", "previous", "results": [ListItem]}`.
  - A ListItem has `id`, `status`, `description` (first 160 characters), `trade`, `services`, `city`, `area`,
    `window_start`, `window_end`, `updated_at` and `confirmed_at`.
  - It never includes the address or access notes.
- `GET /jobs/{id}/` → `Job`. `DELETE /jobs/{id}/` (drafts only) → `204`.

### Attach voice / AI suggestions

`POST /jobs/{id}/source/` `{"transcription_id"?, "interpretation_id"?}` → `Job`.
- **Original text:** set once, from the customer's own transcript or interpretation, and never edited afterwards.
- **Prefill:** the interpretation (`kind: job_description`) fills only **empty** fields, and only with active
  catalog entries that fit together. Services of another trade are dropped, and the city is derived from the area.
- **`preferred_time_text`** is copied as said ("کل شام"). The window is **never** guessed from it.
- **Errors:** `409 request_source_mismatch` when the transcript or interpretation belongs to a different text or
  clip; `not_found` for someone else's objects.

### Edit a draft

`PATCH /jobs/{id}/` with any of the fields below → `Job` (`409 request_not_editable` once confirmed):
- `description`
- `trade`, `services[]`, `services_excluded[]`
- `city`, `area`
- `preferred_time_text`
- `window_start`, `window_end`: ISO 8601. Naive times are read as Asia/Karachi; values are stored and returned in UTC (`…Z`).
- `address_private`, `access_notes`: private; ≤ 500 characters each.
- `budget_pkr`: a decimal ≥ 0, the customer's preference.

The rules below are checked on every save; if any fails the response is `400` and nothing is saved:

| Field | Codes |
|---|---|
| `trade` | `unknown_trade` |
| `services` / `services_excluded` | `unknown_service`, `service_not_in_trade` |
| `services_excluded` | `offered_and_excluded_overlap` |
| `city` / `area` | `unknown_city`, `unknown_area`, `area_not_in_city` |
| `window_end` | `window_end_before_start` |
| `window_start` | `window_in_past`, `window_too_far` (> 90 days) |
| `budget_pkr` | `min_value`, `max_value`, `invalid` |
| unknown fields | `unexpected_field` |

### Confirm

`POST /jobs/{id}/confirm/` → `Job` with `already_confirmed: false`.
- **Requirements:** a description, a trade, at least one service, a city, an area and both window times
  (`required` / `too_few`), and all the rules above, including "not in the past" at the time of confirming.
- **Failure:** `400`, and the draft is unchanged.
- **Idempotent:** repeating the call returns the same request with `already_confirmed: true`, so one request
  still exists.

### Photos

- **Upload:** `POST /jobs/{id}/photos/`, multipart field `image` (drafts only) → `201 Photo`.
  - Accepted: JPEG/PNG/WebP, ≤ 5 MB, at most 5 per request.
  - Checked by content: magic bytes, Pillow decode, format match, ≤ 40 MP, ≥ 50 px.
  - **Re-encoded without metadata**, so EXIF/GPS is removed.
  - Errors: `413 image_too_large`, `415 image_unsupported`, `400 image_dimensions`, `409 too_many_photos`.
- **Delete:** `DELETE /jobs/{id}/photos/{photo_id}/` (drafts only) → `204`.
- **Download:** `GET /jobs/{id}/photos/{photo_id}/content/` → the image, owner only, `private, no-store`.
- Photos are never sent to AI interpretation.

### Job payload

```json
{"id": "…", "status": "draft", "created_at": "…Z", "updated_at": "…Z", "confirmed_at": null,
 "source": {"kind": "voice", "language": "ur", "original_text": "…کل شام کو آ جائیں۔ AC کی service نہیں چاہیے…",
            "audio_clip_id": "…", "transcription_id": "…"},
 "details": {"description": "…", "trade": "electrician", "services": ["elec_fan_install"], "services_excluded": [],
             "city": "islamabad", "area": "isb-g-9", "preferred_time_text": "کل شام",
             "window_start": "2026-11-27T12:00:00Z", "window_end": "2026-11-27T14:00:00Z", "timezone": "Asia/Karachi",
             "address_private": "…", "access_notes": "…", "budget_pkr": "3500.00"},
 "suggestions": {"interpretation_id": "…", "provider": "gemini", "simulated": false, "fields": {…},
                 "missing": [], "uncertain": ["preferred_time_text"], "unmatched_mentions": [], "heard": {}},
 "photos": [{"id": "…", "mime_type": "image/jpeg", "width": 800, "height": 600, "size_bytes": 14873,
             "content_url": "/api/v1/jobs/…/photos/…/content/"}],
 "issues": {"window_start": ["required"]},
 "ready_to_confirm": false}
```

`issues` lists what still blocks confirmation (for drafts). For M6, `apps.jobs.summary.matching_summary(job)` gives
the shareable view without the address, access notes, photos or original audio.

Speech: `POST /audio/synthesise/` now removes invisible direction marks (LRI/PDI, LRM/RLM), which the UI adds to
keep times in order inside Urdu text, before the text reaches the provider.

## Recommendations and invitations (M6)

**Customer endpoints** live under `/jobs/{id}/`.
- Only the request owner can use them: other customers get `404`, and workers get `403 customer_role_required`.
- The request must be **confirmed** (`409 request_not_confirmed` otherwise).

**Worker endpoints** live under `/invitations/`. They return only invitations addressed to the signed-in
worker; anything else is `404`, and customers get `403 worker_role_required`.

### Recommendations (customer)

`GET /jobs/{id}/recommendations/` →

```json
{"request": {"trade": "electrician", "services": ["elec_fan_install"], "city": "islamabad", "area": "isb-g-9",
             "window_start": "…Z", "window_end": "…Z"},
 "shared_preview": {"description": "…", "trade": "…", "services": […], "services_excluded": […], "city": "…",
                    "area": "…", "window_start": "…Z", "window_end": "…Z", "budget_preference_pkr": "3500.00",
                    "has_photos": true},
 "privacy_warnings": ["phone_number", "address"],
 "workers": [{"worker_id": "<opaque profile UUID>", "display_label": null, "trade": "electrician",
              "services_matched": ["elec_fan_install"], "specialities_matched": ["elec_fan_install"],
              "serves_selected_area": true, "verification": {"status": "demo_approved", "simulated": true},
              "is_new": true, "previous_invitation": null,
              "history": {"completed_jobs": 0, "relevant_jobs": 0, "review_count": 0, "average_rating": null},
              "reasons": [{"code": "speciality", "services": ["elec_fan_install"]},
                          {"code": "serves_area", "area": "isb-g-9"}]}],
 "active_invitation": null}
```

**Matching.** A worker is listed only if all of these hold:
1. The account is an active worker account.
2. The profile trade equals the requested trade.
3. The requested area is one of the worker's service areas.
4. The worker offers **every** requested service and lists none of them as not offered.
5. `worker_eligibility(user, profile).receives_requests` is true. That covers a complete profile, an identity
   status accepted here (demo approval counts in demo mode only) and the worker's accepting-requests choice.

**Ranking** (M9), in order:
1. More requested services among the worker's main specialities (relevance first).
2. More customer-confirmed completed jobs that included a requested service.
3. A smoothed visible rating. It is pulled towards a neutral 3.0 as if there were two extra 3-star reviews, so an
   unrated worker ranks as neutral, never as zero, and a single review cannot outrank a long record.
4. More visible reviews.
5. `worker_id`, as a stable tie-breaker.

At most 20 workers are returned. History and ratings come from completed bookings and visible reviews, in two
grouped queries for the whole list.

**Reasons.** Each card explains the match with stored facts:
- `speciality`: the requested services that are listed main specialities.
- `offers`: the requested services the worker offers that are not main specialities.
- `serves_area`: the selected area is one the worker serves.
- `completed_jobs` (M9): `{count, services}`, the confirmed completed jobs that included a requested service.

`history` gives `completed_jobs` (all confirmed), `relevant_jobs`, `review_count` and `average_rating` (`null`
when unrated). `is_new` is true until the first customer-confirmed completed job. Cards never include a name,
phone number, CNIC, registry data or addresses, and no distance is shown.

**Before sending.**
- `shared_preview` is exactly what a worker will receive: `matching_summary(job)` without its internal ID.
- `privacy_warnings` flags free text that looks like a phone number or an address.
- While no invitation is active, the description can be corrected with
  `PATCH /jobs/{id}/shared-description/` `{"description"}`. It returns the Job plus `privacy_warnings`, and is
  `409 invitation_already_active` otherwise.

### Invitations (customer)

- **Send:** `POST /jobs/{id}/invitations/` `{"worker_id"}`.
  - `201` with a new invitation (`created: true`), or `200` with the existing one when the same worker is
    already invited (`created: false`).
  - `409 invitation_already_active` (`details.invitation_id`) when a different worker is already invited.
  - `400 worker_id: worker_not_available` when the worker no longer matches or is no longer eligible. Both are
    re-checked when sending, even if the worker was listed earlier.
- **History:** `GET /jobs/{id}/invitations/` → `{"results": [Invitation]}`, newest first.
- **Withdraw:** `POST /jobs/{id}/invitations/{invitation_id}/withdraw/` → the Invitation.
  - Idempotent for an already-withdrawn invitation.
  - `409 invitation_closed` if the worker already declined.

```json
{"id": "…", "status": "active", "worker": {"worker_id": "…", "display_label": null, "trade": "electrician"},
 "created_at": "…", "seen_at": null, "closed_at": null, "decline_reason": null}
```

### Invitations (worker)

- **Inbox:** `GET /invitations/?status=active|declined|withdrawn&page=…` → paginated, newest first.
- **Open:** `GET /invitations/{id}/` → the WorkerInvitation; the first open sets `seen_at`.
- **Decline:** `POST /invitations/{id}/decline/` `{"reason"?: "not_available"|"too_far"|"not_my_work"|"other"}` →
  the WorkerInvitation.
  - Idempotent for an already-declined invitation.
  - `409 invitation_closed` if the customer withdrew it.

```json
{"id": "…", "status": "active", "created_at": "…", "seen_at": "…", "closed_at": null, "decline_reason": null,
 "job": {"description": "…", "trade": "…", "services": […], "services_excluded": […], "city": "…", "area": "…",
         "window_start": "…Z", "window_end": "…Z", "budget_preference_pkr": "3500.00", "has_photos": true}}
```

**What workers never receive:**
- the exact address or access notes;
- photos or the original recording or transcript;
- the customer's identity or phone number;
- the job ID.

Workers still cannot open `/jobs/…` (`403`).

**Rules:**
- At most **one active invitation per request**. This is enforced by a PostgreSQL partial unique index, plus a
  row lock on the request while sending.
- Declining or withdrawing frees the slot. Inviting again, even the same worker, creates a **new** invitation ID.
- Closed invitations stay as history.
- An invitation never reserves time. Accepting a quote creates a booking (M8); the invitation stays `active` while
  booked (messages continue). Payloads carry `booking: {id, status}`, and cancelling the booking closes the
  invitation as `cancelled`.

## Conversations, quotes and agreement gaps (M7)

Everything lives under `/conversations/{invitation_id}/`. One conversation belongs to one invitation.

**Who can use it.** Only the request owner and the invited worker. Anyone else, including another worker or
another customer, gets `404` for every endpoint, so the conversation's existence is not revealed.

**Writes.** Sending messages, saving or sending quotes, resolving points and manual review need an **active**
invitation. Otherwise they return `409 conversation_closed`. After a decline or withdrawal, messages and all quote
versions stay readable to both people. Rate limit: `conversation_user` 600/hour per account.

### Header

`GET /conversations/{id}/` →

```json
{"invitation": {"id": "…", "status": "active", "created_at": "…Z", "closed_at": null},
 "role": "customer", "can_write": true,
 "job": {"description": "…", "trade": "…", "services": […], "services_excluded": […], "city": "…", "area": "…",
         "window_start": "…Z", "window_end": "…Z", "budget_preference_pkr": "3500.00", "has_photos": false},
 "job_id": "<request ID: customer only, null for the worker>",
 "counterpart": {"role": "worker", "worker_id": "…", "trade": "electrician"}}
```

- `job` is the invitation's shared summary from M6. The worker never receives the address, access notes,
  photos, original recording or customer identity.
- The worker's `counterpart` is just `{"role": "customer"}`.

### Messages

- **List:** `GET …/messages/` returns the newest page (30) as `{"results": [Message], "has_more_before": bool}`,
  oldest first.
  - `?after=<message_id>` returns newer messages (polling). The app polls every 5 s and only appends, so text
    being typed is never touched.
  - `?before=<message_id>` returns the previous page.
  - An unknown cursor is `400 cursor: invalid`.
- **Send:** `POST …/messages/`.
  - Text: `{"client_id": "<uuid made on the device>", "kind": "text", "text": "…"}` (1–1000 characters).
  - Voice: `{"client_id", "kind": "voice", "audio_clip_id", "transcription_id"?, "text"?}`.
  - `201` with the new Message.
  - **Retries are safe:** the same `client_id` from the same sender returns `200` with the original message.
    That holds even after the invitation closed. The device keeps the ID until a send succeeds.
- **Voice notes:**
  1. Upload the recording with `POST /audio/clips/`, `purpose: "message"`. It stays private to the uploader
     until it is sent.
  2. Optionally get a proposed caption with `POST /audio/transcribe/`.
  3. Send the voice note with the caption the sender reviewed or edited in `text`.
  - `caption_status` is one of:
    - `approved`: a transcription was used and the sender checked it;
    - `typed`: the sender wrote it without a transcription;
    - `unavailable`: no caption, and the app shows "Caption unavailable".
  - The original audio and the approved caption are stored separately. The automatic proposal
    (`interpreted_text`) is shown only to its sender.
  - A clip can be used only once, only by its owner, and only with purpose `message`. Otherwise the response is
    `400 audio_clip_id: not_found`. A transcription of another clip is `400 transcription_id: not_found`.
- **Playback:** `GET …/messages/{message_id}/audio/` returns the original audio, for the two people only, with
  `Cache-Control: private, no-store`.
- Messages cannot be edited or deleted.

```json
{"id": "…", "client_id": "<only on your own messages>", "sender_role": "worker", "mine": false, "kind": "voice",
 "text": "میں کل شام پانچ بجے آ سکتا ہوں۔ …", "caption_status": "approved", "interpreted_text": null,
 "audio_url": "/api/v1/conversations/…/messages/…/audio/", "duration_seconds": 2.0, "created_at": "…Z"}
```

### Quotes

A quote is a set of **structured terms**. Money is a decimal string in PKR, and the server computes every total.

| Field | Values |
|---|---|
| `inspection_only` | `true` for an inspection visit only. Needs `visit_fee` and a treatment of `charged` or `waived_if_hired`. The repair price stays unknown. |
| `scope` | What the work covers (required). |
| `quantity` | 1–999. Required when `labour_basis` is `per_item`. |
| `labour_amount`, `labour_basis` | `total` (whole job) or `per_item` (amount × quantity). |
| `materials` | `included` (in the price) · `worker_extra` (the worker brings them, charged separately) · `customer` (the customer supplies them) · `none`. |
| `materials_amount` | Only with `worker_extra`. Leave it empty while unknown. |
| `visit_fee`, `visit_fee_treatment` | Treatment is `none` · `charged` · `waived_if_hired` · `included`. |
| `exclusions` | Work not covered. |
| `start_at`, `end_at` | ISO timestamps. A time without an offset is read as Asia/Karachi; responses are UTC `…Z`. `end_at` must be after `start_at`. The start cannot be in the past or more than 90 days ahead. |

**Totals.** `totals` is `{labour_total, materials_total, visit_total, known_total, unknown: ["materials"|"labour"|"repair"], complete}`.
An unknown amount is never shown as zero: `known_total` adds up only the known parts, and `complete` is `false`
while anything is unknown.

**Endpoints:**
- **Listing:** `GET …/quotes/` → `{"current": Quote|null, "draft": Quote|null, "history": [Quote], "readiness": Readiness}`.
  - `draft` is visible to the worker only.
  - `history` holds superseded versions, newest first, each with its own findings.
- **Draft (worker only; the customer gets `403 worker_only`):**
  - `PUT …/quotes/draft/` saves all fields and returns the draft. The draft includes `issues`, which lists the
    field error codes it would fail on if sent.
  - `DELETE …/quotes/draft/` discards it (`204`).
- **Send:** `POST …/quotes/draft/submit/` → `201` Quote.
  - Validation failures return `400` with `fields`. Codes: `required`, `amount_out_of_range`,
    `quantity_out_of_range`, `materials_amount_not_applicable`, `visit_fee_treatment_missing`,
    `inspection_fee_treatment`, `window_end_before_start`, `window_in_past`, `window_too_far`.
  - Returns `409 no_quote_draft` when there is no draft.
  - The version gets the next number, and the previous version becomes `superseded`.
  - **Submitted versions are frozen**; a database constraint backs this. To change anything, send a new version.
- **One version:** `GET …/quotes/{quote_id}/` → the Quote plus `readiness` for that version.

**Expiry.** `expires_at = min(submitted_at + QUOTE_VALIDITY_HOURS (24), start_at)`. An expired version is not
ready.

**Concurrency.** Sending locks the request, then the invitation, then the draft. That is the same order M6
uses to send an invitation, and withdraw/decline lock the invitation. The invitation is checked again inside the
transaction, so a quote can never be submitted after its invitation closed. A double submit creates one
version.

### Agreement check (GAP-01)

When a version is sent, the server runs two checks:
1. **Deterministic rules:**
   - `timing_differs` (blocking; the customer answers): the proposed time falls outside the requested window.
   - `materials_amount_unknown` (a note, not blocking).
2. **The configured checker** (`AGREEMENT_CHECK_PROVIDER`: `fixture` in demo · `gemini` · `unconfigured`). It
   receives only the shared request summary, the message texts the senders approved (the last 40) and the quote
   terms, with all times in one Asia/Karachi format. It never receives the address, access notes, photos, audio,
   names or phone numbers.

Every checker finding must quote its **source statements**. A finding whose quoted text does not appear in the
input is dropped. Each finding is tied to that quote version.

`check.status` is one of:
- `running` (M8): an attempt is in progress, and acceptance waits. Every run gets a new attempt ID. The provider
  is called outside any transaction. The result is saved only if, under a row lock, the same attempt is still
  current, the version is still the submitted one and it has not been accepted; late or stale results are
  discarded. A run still `running` after `AGREEMENT_CHECK_STALE_SECONDS` (180) is shown as `unavailable` with
  `failure: "stalled"`, so it can be re-run or reviewed manually.
- `passed`: the check ran and found nothing.
- `findings`: the check found points to clarify.
- `unavailable`: the checker could not run. **This is never shown as a pass.** `check.failure` holds the error
  code, for example `ai_provider_unavailable`.
- `not_run`.

`check.simulated` is `true` for the fixture.

**Related actions:**
- **Run again:** `POST …/quotes/{id}/check/`. Allowed only when the status is `not_run` or `unavailable`;
  otherwise `409 check_not_needed`.
- **Manual review** (customer only, only when the check is `unavailable`): `POST …/quotes/{id}/manual-review/`.
  It is recorded as a manual review, not as a passed check.
- **Resolve a point:** `POST …/quotes/{id}/findings/{finding_id}/resolve/`
  `{"resolution": "terms_confirmed"|"terms_changed", "note": "what was agreed" (3–500)}`.
  - `terms_confirmed`: the version as written is what both meant, so the point is resolved.
  - `terms_changed`: the clarification changed price, scope, materials or timing. The point is recorded, but
    **this version stays blocked** (`revision_required`) until the worker submits a revised quote, which is
    checked again.
  - A point cannot be dismissed without a note. Who resolved it, their role and when are recorded, and kept
    with that version.
  - Older and superseded versions return `409 quote_not_current`.

```json
{"id": "…", "source": "ai", "code": "materials_responsibility", "blocking": true, "ask": "worker",
 "question": "گاہک سمجھتے ہیں کہ سامان شامل ہے، مگر قیمت میں سامان شامل نہیں۔ …",
 "sources": [{"kind": "request", "ref": "description", "text": "1200 روپے سامان سمیت۔"},
             {"kind": "quote", "ref": "materials", "text": "customer"}],
 "status": "open", "resolution": null, "resolution_note": null, "resolved_role": null, "resolved_at": null}
```

Codes are `materials_responsibility`, `quantity_mismatch`, `price_basis`, `visit_fee`, `scope_mismatch`,
`timing_mismatch`, `other` and the two rule codes. Blocking points stop readiness until they are resolved; notes
only add a warning.

### Readiness (used by M8 acceptance)

`GET …/readiness/` →

```json
{"invitation_id": "…", "quote_id": "…", "version": 2, "expires_at": "…Z", "ready": true, "blocking": [], "warnings": [],
 "booking_id": null}
```

`blocking` codes are `already_booked`, `invitation_not_active`, `no_quote`, `quote_not_submitted`,
`quote_superseded`, `quote_expired`, `unresolved_findings`, `revision_required`, `automated_check_not_run`,
`automated_check_running`, `automated_check_unavailable` (until the customer's manual review) and
`worker_not_eligible`. `warnings` codes are `open_notes` and `unknown_amounts`.

A ready version can be accepted with `POST /bookings/` (below). The conversation header also carries
`booking: {id, status}`.

## Bookings, arrival codes and changes (M8)

Everything lives under `/bookings/`. Only the booking's customer and its assigned worker can see or act on a
booking. Anyone else gets `404` (the booking's existence is not revealed). An action that belongs to the other
participant returns `403 not_allowed_for_role`.

**Rate limits:**
- `booking_user`: 300/hour per account, for writes.
- `arrival_code_issue_user`: 10/hour.
- `arrival_code_verify_user`: 20/hour.

### Accept a quote (BK-01, BK-03)

`POST /bookings/` (customer only) with:

```json
{"invitation_id": "…", "quote_id": "…", "version": 2, "idempotency_key": "<uuid made on the device>"}
```

It returns `201` with the Booking (`created: true`).

**Retries and keys:**
- **A retry with the same key returns `200` with the same booking** (`created: false`), whatever happened to it
  since.
- The same key sent with a different invitation or quote is `409 idempotency_key_reused` (`details.booking_id`).
- The app keeps the key until the outcome is known. After a dropped connection it re-reads the conversation
  (`booking`) before offering "accept" again.

**One transaction, locks taken in this order** (shared with M6/M7): job → invitation → quote → worker profile →
worker account. Each row is re-read under its lock. Then the server checks:

| Check | Error (`409` unless noted, with the current state in `details`) |
|---|---|
| You own the job | `404` |
| No other booking for the job | `job_already_booked` (`booking_id`) |
| The invitation is still active | `invitation_not_active` (`invitation_status`) |
| This exact version is the current one | `quote_not_current` (`current_quote_id`, `current_version`) |
| The quote has not expired | `quote_expired` (`expires_at`) |
| M7 readiness: no open points, check finished, nothing "terms changed" | `quote_not_ready` (`blocking`) |
| `worker_eligibility(...).can_take_jobs` | `worker_not_eligible` |
| No overlapping booking of that worker, using `[start, end)` (adjacent slots are fine) | `schedule_conflict` |

**Accepting work while paused:** a worker who has paused new requests can still be booked for a quote they
sent. The pause controls new invitations only.

**Database guarantees (PostgreSQL)** back these checks:
- one non-cancelled booking per job;
- one booking per acceptance key per customer;
- an **exclusion constraint** on `(worker, tstzrange(start, end, '[)'))` while the booking is
  confirmed, arrived or in progress;
- at most one job in progress per worker.

Tests on real concurrent connections cover:
- two customers accepting overlapping slots at once (one booking);
- a double tap with one key (one booking);
- accept against withdrawal;
- accept against a revision.

**What changes after acceptance:**
- **Quotes freeze.** On the booked job, draft save or discard, submit, re-check, resolve and manual review all
  return `409 job_already_booked` (`booking_id`).
- **Invitations:**
  - new invitations return `409 job_already_booked`;
  - withdraw and decline return `409 invitation_booked` (`booking_id`), so the user is sent to the booking.
- **Messages continue.**
- **Address:** the exact address and access notes go to the assigned worker on the booking only, never in
  conversation or invitation payloads.

### Booking

- `GET /bookings/?status=` → paginated cards, for the customer's own bookings or the worker's assigned ones.
- `GET /bookings/{id}/` →

```json
{"id": "…", "status": "confirmed", "role": "worker", "invitation_id": "…", "job_id": null, "quote_id": "…", "quote_version": 2,
 "start_at": "…Z", "end_at": "…Z", "timezone": "Asia/Karachi",
 "terms": {"scope": "…", "quantity": 2, "labour_amount": "600.00", "…": "…", "totals": {…}, "source": {"kind": "quote", "version": 2}},
 "accepted_terms": {"…same terms…", "quote_id": "…", "version": 2, "accepted_at": "…Z",
                    "check": {"status": "passed", "provider": "fixture", "simulated": true, "manual_review_at": null},
                    "resolutions": [{"code": "materials_responsibility", "resolution": "terms_confirmed", "note": "…"}]},
 "terms_changed": false, "job": {…shared summary…},
 "address": {"address": "…", "access_notes": "…"},
 "counterpart": {"role": "customer"},
 "arrived_at": null, "started_at": null, "cancelled_at": null, "cancelled_role": null, "cancel_reason": null, "cancel_note": null,
 "arrival_code": {"active": true, "expires_at": "…Z", "attempts_remaining": 5, "expired": false, "locked": false, "used_at": null},
 "changes": [...], "history": [{"kind": "confirmed", "to_status": "confirmed", "actor_role": "customer", "at": "…Z"}],
 "actions": {"arrive": true, "issue_code": false, "start": false, "cancel": true, "propose_change": true, "change_time": true}}
```

**Field notes:**
- `accepted_terms` never changes; the model refuses to overwrite it. `terms` are the terms in effect.
- `address`:
  - the customer always sees their own address;
  - the worker sees it only while the booking is confirmed, arrived or in progress;
  - otherwise it is `null`.
- `counterpart`: for the customer it is the worker's opaque reference, trade and identity status (labelled when
  simulated). The worker never receives the customer's identity.
- `arrival_code`: whether a code is active, for both roles. **It never contains the code or its digest.**

### Arrival, code and start (BK-04, BK-05)

The booking moves **Confirmed → Arrived → In progress**.

- `POST /bookings/{id}/arrive/` (assigned worker only): `confirmed` → `arrived`. A retry is harmless.
- `POST /bookings/{id}/arrival-code/` (owning customer only; only when `arrived`) returns the Booking plus
  `"code": {"value": "482913", "expires_at": "…Z"}`.
  - **This response is the only place the code appears** (`Cache-Control: no-store`).
  - The code is six digits from `secrets`. Only `HMAC-SHA256(SECRET_KEY-derived key, booking_id:code)` is stored.
  - It expires after `ARRIVAL_CODE_TTL_MINUTES` (15).
  - Issuing again invalidates the previous code.
  - Codes are never logged and never sent to read-aloud.
- `POST /bookings/{id}/start/` `{"code": "482 913"}` (assigned worker only; spaces are ignored):
  - A wrong code returns `400 code_incorrect` (`details.attempts_remaining`). **The failed attempt is saved even
    though the call fails.**
  - After `ARRIVAL_CODE_MAX_ATTEMPTS` (5) wrong attempts the response is `429 too_many_attempts`, and the
    customer must issue a new code.
  - An expired code is `400 code_expired`; no code at all is `400 no_active_code`.
  - On success the code is used once and the booking becomes `in_progress`.
  - **Starts are serialised per worker:** if another of the worker's jobs is in progress, the response is
    `409 worker_has_job_in_progress`, even when the planned times do not overlap.
  - Any other status gives `409 booking_state_conflict`.

The code confirms arrival for this booking only. It does not prove identity, location, skills or safety, and
the customer screen says so.

### Cancellation (before start)

`POST /bookings/{id}/cancel/` `{"reason": "not_available"|"changed_plans"|"no_show"|"other", "note"?}`:
- Either participant can cancel while the booking is `confirmed` or `arrived`. `other` needs a note.
- The cancellation:
  - frees the worker's time;
  - closes the invitation (status `cancelled`), so its quote can never be accepted again;
  - invalidates live codes;
  - closes pending changes.
- After the start it returns `409 cancel_not_allowed`; the issue and dispute route is M9.
- The customer can then invite again from the request (a new invitation and conversation).

### Changes after booking (QT-04)

- `POST /bookings/{id}/changes/` proposes the full set of terms (same fields as a quote draft) plus a `note`
  (3–500). The proposer's approval is recorded at once.
- `POST /bookings/{id}/changes/{change_id}/approve/` or `/reject/` is for the other participant only.
  `/withdraw/` is for the proposer only.
- **The terms in effect change only when both have approved.** The change keeps `old_terms` and `new_terms`;
  `accepted_terms` keeps the original agreement.
- One pending change at a time (`409 change_pending`).
- A proposal that changes nothing returns `400 non_field_errors: no_change`.
- Time changes:
  - only before arrival (`409 time_change_not_allowed`);
  - re-checked for overlaps when proposed and again, under the worker lock, when approved
    (`409 schedule_conflict`).
- Scope and price changes are also allowed during the job (for example a third fan).

Completion, disputes and reviews continue below (M9).

## Completion, disputes and reviews (M9)

The booking life cycle continues from M8:

```
in_progress → completion_requested (worker) → completed (customer confirms)
                                            → disputed (customer raises an issue) → in_progress | closed (staff, Django Admin)
```

**Reservations and starts:**
- `completion_requested` and `disputed` keep the worker's reservation: the no-overlap exclusion constraint covers
  `confirmed, arrived, in_progress, completion_requested, disputed`.
- They also count as the worker's current job: `booking_one_started_per_worker` covers `in_progress,
  completion_requested, disputed`, and so does the service check. Another job cannot start, even after the
  planned end, and the response is `409 worker_has_job_in_progress`.
- `completed` (confirmed by the customer) and `closed` (by staff) release the worker.
- The worker's accepting-requests preference, the accepted terms and the change history are never touched.

**Retries and races:** all actions lock job → worker → booking (the M8 order) and are retry-safe. Repeating an
action returns the booking without a second event. A confirm racing a dispute leaves exactly one of them applied;
the other gets `409 booking_state_conflict` with the current `status`.

### Endpoints

- **`POST /bookings/{id}/request-completion/`** (assigned worker): `in_progress` → `completion_requested`.
  - While a change proposal is pending: `409 change_open` (`details.change_id`, `number`). Approve, reject or
    withdraw it first. The booking shows `actions.completion_blocked_by_change`.
  - Changes cannot be proposed or approved during `completion_requested` or `disputed` (`409
    booking_state_conflict`).
- **`POST /bookings/{id}/confirm-completion/`** (owning customer): `completion_requested` → `completed`.
  - The booked catalog services are recorded as `completed_services`: the request's explicit tags, never
    inferred from review text and never the worker's whole profile.
  - The worker never completes a booking alone, and a booking stays `completion_requested` until the customer
    answers.
- **`POST /bookings/{id}/raise-issue/`** (owning customer) `{"reason": "not_finished"|"not_as_agreed"|"damage"|"price"|"other", "note": 3–500}`:
  `completion_requested` → `disputed`.
- **Staff outcome:** not an API. It is done in Django Admin with the `bookings.resolve_dispute` permission:
  Bookings → a disputed booking → **Record dispute outcome**.
  - The outcome is `return_to_work` (→ `in_progress`) or `close` (→ `closed`), with a reason.
  - `close` also closes the invitation (status `cancelled`): the conversation becomes read-only, and the quote
    can never be reused.
  - The booking shows `staff_outcome` and `staff_reason` to both participants; staff identity is not shown.
  - A `closed` booking is not completed work and can never be reviewed.

**New booking fields:**
- `completion_requested_at`, `completed_at`, `completed_services`;
- `disputed_at`, `dispute_reason`, `dispute_note`;
- `closed_at`, `staff_outcome`, `staff_reason`;
- `review`.

`actions` gains `request_completion`, `completion_blocked_by_change`, `confirm_completion`, `raise_issue` and
`review`. History event kinds gain `completion_requested`, `completed`, `disputed`, `staff_resolved` (actor role
`staff`) and `reviewed`. Booking cards gain `review_submitted`.

### Reviews

`POST /bookings/{id}/review/` (owning customer) with
`{"rating": 1–5, "text"?: ≤500, "audio_clip_id"?, "transcription_id"?}`:

- Returns `201` with the Review the first time. A repeat returns `200` with the stored review
  (`created: false`); the first review is never replaced.
- One review per booking (`review_one_per_booking`, unique in PostgreSQL). Ratings must be 1–5
  (`review_rating_1_to_5`).
- Reviews are allowed only on a `completed` booking. Every other status (cancelled, in progress, awaiting
  confirmation, disputed, closed by staff) returns `409 review_not_allowed` (`details.status`). The worker gets
  `403 not_allowed_for_role`, and other accounts get `404`.
- **Voice draft:**
  1. Upload the recording with `POST /audio/clips/`, `purpose: "review"`. It stays owner-only.
  2. `POST /audio/transcribe/` proposes an Urdu draft.
  3. The customer edits it and sends it as `text`.
  - The proposal is stored separately (`interpreted_text`, shown to the author only). Typed reviews need no
    audio.
- The review's `services` are the booking's `completed_services`.

```json
{"id": "…", "rating": 5, "text": "کاریگر وقت پر آئے …", "source": "voice", "services": ["elec_fan_install"],
 "created_at": "…Z", "hidden": false, "interpreted_text": "…author only…", "created": true}
```

**Hiding:** done in Django Admin with the `reviews.hide_review` permission: Reviews → **Hide review…** with a
reason.
- The original text is never edited. `hidden_at`, `hidden_by` and `hidden_reason` are stored.
- A hidden review disappears for the worker (booking and feedback) and from every rating and count. Its author
  still sees it, marked `hidden: true`.

### Worker feedback

`GET /bookings/feedback/` (worker) →

```json
{"completed_jobs": 1, "review_count": 1, "average_rating": "5.0",
 "jobs": [{"booking_id": "…", "completed_at": "…Z", "trade": "electrician", "area": "isb-g-9",
           "services": ["elec_fan_install"], "review": {"rating": 5, "text": "…", "…": "…"}}]}
```

- `average_rating` has one decimal, or is `null` when there are no visible reviews (**never zero**).
- Only customer-confirmed completed bookings count. Jobs show the area only: no address, access notes or
  identities.
