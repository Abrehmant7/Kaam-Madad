# Kaam Madad — API Contracts

All endpoints are under `/api/v1/`, return JSON, and are served from the same origin as the web app.
Implemented through **M6**. Planned endpoint families for later modules are listed in
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
| 403 | Signed in / identified but not allowed | `permission_denied`, `csrf_failed`, `account_inactive`, `worker_role_required`, `customer_role_required`, `marketplace_role_required` |
| 404 | Unknown resource or `/api/` path | `not_found` |
| 409 | Conflicts with current state | `already_authenticated`, `phone_already_confirmed` |
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

**Ranking.** Workers with more requested services among their main specialities come first. Ties are broken by
`worker_id` (stable, and not tied to sign-up time). At most 20 workers are returned.

**Reasons.** Each card explains the match with stored facts:
- `speciality`: the requested services that are listed main specialities.
- `offers`: the requested services the worker offers that are not main specialities.
- `serves_area`: the selected area is one the worker serves.

Every worker has `is_new: true` because completed jobs and reviews arrive in M9. Cards never include a name,
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
- An invitation never reserves time or confirms a booking (M8).
