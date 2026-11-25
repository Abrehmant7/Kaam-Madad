# Kaam Madad — API Contracts

All endpoints are under `/api/v1/`, return JSON, and are served from the same origin as the web app.
Implemented through **M3**. Planned endpoint families for later modules are listed in
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
