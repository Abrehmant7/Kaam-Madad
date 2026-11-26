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
| M4 Worker onboarding and identity check | ✅ Complete (27 Nov 2026) — real Tesseract OCR verified on synthetic cards; registry simulated |
| M5 Customer and job requests | ✅ Complete (27 Nov 2026) — fixture and live voice checks recorded |
| M6 Recommendations and invitations | ✅ Complete (27 Nov 2026) |
| M7 Communication and agreements | ⬜ Next |
| M8 Booking and arrival | ⬜ Not started |
| M9 Completion and feedback | ⬜ Not started |
| M10 Reporting and moderation | ⬜ Not started |
| M11 Integration and delivery | ⬜ Not started |

---

## M6 Recommendations and invitations — complete (27 Nov 2026)

### Delivered

- [x] `GET /jobs/{id}/recommendations/` (owner only, confirmed requests). It matches on trade, area, coverage of
  all requested services and no explicit exclusion, plus `worker_eligibility(...).receives_requests`. Ranked by
  requested services among main specialities, with a stable `worker_id` tie-breaker. It returns reasons from
  stored facts and minimal public cards (no name, phone, CNIC, registry data or addresses).
- [x] **`Invitation` model** (migration `invitations.0001`):
  - Statuses: active / declined / withdrawn.
  - Stable UUID, history kept, `shared_summary` = `matching_summary(job)` at send time.
  - One active invitation per request: PostgreSQL partial unique index plus a row lock on the request. A retry
    to the same worker returns the same invitation; a different worker gets `409`.
  - The worker is re-checked when sending.
- [x] **Customer:**
  - **Find a worker** on the confirmed request; cards with reasons; empty state.
  - A preview of exactly what will be shared and what is not, with phone and address warnings and a
    description edit before sending.
  - Send, see status and "seen", withdraw, history. State survives a refresh.
- [x] **Worker:**
  - A **Job invitations** inbox on the dashboard (own invitations only).
  - The invitation page with task, area, requested window, description and budget preference, plus read-aloud
    (shareable fields only).
  - Decline with an optional reason.
- [x] `seed_demo_workers` (fictional, demo mode only) for rehearsals.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **277 passed**: 18 new for M6, including **2 real concurrency tests** (threads, separate connections): 4 racing sends → 1 active; 3 racing retries → 1 invitation |
| `check`, `makemigrations --check` | ✅ No issues, no pending migrations |
| Frontend typecheck / tests / build | ✅ No errors / **71 passed** / built |

Backend tests cover:
- Eligible workers appear in a stable order with the right reasons.
- Paused, unapproved (none or in progress), wrong-area, wrong-trade, explicitly excluded and inactive workers
  stay out, and demo approval is ignored in live mode.
- A worker who becomes ineligible after being listed (paused or suspended) cannot be invited.
- Decline and withdraw free the slot, and re-inviting gives a new ID.
- Unrelated workers get 404; customers get 403 on worker endpoints, and workers 403 on jobs.
- Worker payloads contain only the 10 shareable fields.
- The description edit and privacy warnings work.

### Two-browser walk-through (two separate Chrome sessions at 360 px, real backend, fixture TTS)

1. **Customer (Urdu)** with a confirmed G-9 fan installation request opened **Find a worker**.
   - Five matching demo-approved electricians: four with fan installation as their main speciality, in stable
     `worker_id` order, then demo worker 03009990102, whose main speciality is something else. The paused demo
     worker was absent.
   - The preview flagged the phone number typed in the description; the customer removed it and sent to worker
     03009990101. After a refresh the state was unchanged.
2. **Worker A (second browser)** logged in and found it in the **Job invitations** inbox.
   - Opened it: the description without the phone number, and no address or access notes. The API exposed only
     the 10 shareable fields.
   - Read it aloud, then declined with "too far". It stayed declined after a refresh.
   - The customer, after a refresh, saw "Seen by the worker" and then "Declined", and the earlier decline was
     noted on the card.
3. **Slot rules:**
   - Send to B → `201`; retry B → `200` (same invitation); send A while B is active → `409 invitation_already_active`.
   - Withdraw B, then re-invite A → `201` with a **new** invitation ID.
   - Worker A's inbox then showed the new active invitation plus its history.
4. **Other accounts:** worker B got `404` on A's invitation (view and decline) and `403` on the customer's job.
   After worker B paused requests, inviting B gave `400 worker_not_available` and B dropped out of the list.
5. **Layouts:** Urdu and English; no horizontal overflow.

**Fixed:** `matching_summary` formatted the same instant differently depending on how the datetime was loaded.
It now always uses UTC `…Z`. In the preview, warnings now refer to the saved description, so they no longer
linger while the customer edits it.

### Known limitations

- **No display name:** there is no approved public display name, so cards show the trade plus a short reference
  (e.g. "Electrician · ref. A7F3").
- **Basic matching:** all-services coverage only. There is no distance, availability, review or completed-job
  history yet (M8/M9), so every worker is shown as new.
- **Inbox updates:** the worker inbox refreshes on load. There are no push notifications (polling or real-time
  updates come later).

## M5 Customer job requests — complete (27 Nov 2026)

### Delivered

- [x] **Customer dashboard:** **Describe your job**, **My requests** (drafts to resume, confirmed requests to
  reopen) and phone confirmation. Signup and phone confirmation are unchanged.
- [x] **Step 1, describe:**
  - Record, upload or type, in Urdu or English, reusing the M3 `VoiceCapture` and the `job_description`
    interpretation API.
  - The draft is saved before any provider call, so it survives provider errors and reloads.
  - Manual path ("Continue without suggestions").
- [x] **Step 2, details:**
  - The original input is shown verbatim, including negations.
  - Editable suggestions, marked "Please check"; unmatched mentions are listed.
  - Trade and services, with work not needed under "More options"; city and area.
  - **Exact date, start and end time.** "کل شام" is shown with a prompt; times are never guessed.
  - Private address and access notes, a budget preference, and up to 5 photos.
- [x] **Step 3, review:**
  - A plain-language summary.
  - **Read aloud** (M3 `ReadAloud`) of the work, area, date and time only.
  - Copy saying confirmation saves and does not invite or reserve.
  - Confirm, then the request detail page.
- [x] **Backend `apps.jobs`:**
  - `JobRequest` (customer-owned; original input plus owned source references kept apart from confirmed
    details; UTC window; `DecimalField` budget preference; private address and access notes) and `JobPhoto`.
  - Migration `jobs.0001`.
- [x] **Server validation:**
  - Catalog relationships: services in the trade, area in the city, no overlap.
  - Time window: end after start, not in the past, at most 90 days ahead.
  - Required fields are checked on confirmation. Confirmation is idempotent (row lock), and a failed
    confirmation leaves the draft unchanged.
- [x] **Ownership:** every lookup is scoped to the session's customer (others get 404); workers get 403.
  Audio, transcripts and interpretations can only be attached by their owner.
- [x] **Photos:** content-checked, re-encoded without metadata (EXIF/GPS removed), private owner-only
  downloads, never sent to AI.
- [x] **M6 hand-off:** `apps.jobs.summary.matching_summary(job)` gives a confirmed request without the address,
  access notes, photos or original audio.

### Voice and AI checks: fixtures vs live

| Check | Providers | Result |
|---|---|---|
| Urdu voice request recorded in Chrome with a fake microphone | **Fixtures** (STT, interpretation, TTS) | Transcript kept verbatim, with "کل شام" and "AC کی service نہیں چاہیے". Prefilled electrician, fan installation, G-9; time phrase flagged; window empty until chosen; confirmed |
| English typed request | **Fixture** interpretation | Plumber, tap, G-10; "No geyser work" → geyser **not needed** (after the negation fix below) |
| Provider failure | `INTERPRETATION_PROVIDER=unconfigured` | Error shown, draft kept, listed after a reload, finished manually and confirmed |
| Urdu voice note (fictional, made with live ElevenLabs) uploaded | **Live Gemini** `gemini-3.6-flash` from `.env` | ❌ Google `503` "high demand" and a timeout on two runs. The UI showed the error and kept the draft, as designed |
| Same voice note | **Live Gemini `gemini-3-flash-preview`** (model overridden for this run only) + **live ElevenLabs** | ✅ Transcript in 12.7 s: "میرے گھر میں دو پنکھے لگوانے ہیں G9 Islamabad میں۔ کل شام کو آ جائیں۔ AC کی service نہیں چاہیے۔". Prefilled electrician, fan installation, G-9 and "کل شام"; time prompt shown; ElevenLabs read the summary (`simulated: false`) without the address; confirmed |

### Browser walk-through (Chrome, 360 px, real backend), 27 Nov 2026

1. **Urdu customer:**
   - Signup from "مجھے کاریگر چاہیے", then an empty dashboard.
   - Record, details, **page reload** (the draft was still prefilled).
   - Details: description, 17:00–19:00 tomorrow, address, access, budget 3500, and a photo **with GPS EXIF**.
   - Review: read aloud excluded the address and access notes.
   - Confirm, then the detail page; after a reload it was listed as confirmed.
   - **Stored UTC** `12:00Z–14:00Z` (17:00–19:00 Karachi).
   - **Second confirm:** `200 already_confirmed: true`, with **1** request in total.
   - **Stored photo:** no `Exif` and no camera make; `private, no-store`.
2. **Server rejections, from the browser:**
   - Cross-trade service → `service_not_in_trade`.
   - Area outside the city → `area_not_in_city`.
   - End before start → `window_end_before_start`.
   - Yesterday → `window_in_past`.
   - A fake JPEG → `415 image_unsupported`.
3. **Another customer and a worker:** another customer got view, edit, confirm and photo → **404**, with an empty
   list. A worker got the list and detail → **403**.
4. **English typed request:** typed → details → review → confirm → **reopened from My requests**, with the
   original text shown.
5. **Regression:** the M4 walk-through (worker signup, three screens, refresh and login resume, real Tesseract
   scan, demo approval, customer signup) passed again.
6. **Width:** no horizontal overflow at 360 px in Urdu or English.

The walk-through found and fixed:
- Urdu screens showed the time range out of order ("PM – 7:00 PM 5:00"). Time ranges are now in LTR isolates,
  and the server strips these invisible marks before speech synthesis (tested).
- Urdu text starting with "G-9" was laid out left to right. Direction is now chosen by the dominant script.
- The simulated (fixture) interpreter missed English "no …" negations. It now matches `no`, `without` and
  `never` as whole words.
- Running many test sign-ups in an hour hit the signup rate limit (30 per hour per IP), as intended. The local
  throttle counters were cleared to finish the walk-through.

### Automated checks

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **259 passed** (25 new for M5, plus fixture-negation and speech-text cleaning tests) |
| `check`, `makemigrations --check` | ✅ No issues, no pending migrations |
| Frontend typecheck / tests / build | ✅ No errors / **66 passed** / built |

### Known limitations

- **Live Gemini:** `gemini-3.6-flash` (the model in `.env`) answered 503 throughout the live check;
  `gemini-3-flash-preview` worked. Set `GEMINI_STT_MODEL`/`GEMINI_INTERPRETATION_MODEL` accordingly, or retry later.
- **Fixture interpretation:** keyword rules (e.g. "leaking" is not matched to "leak repair"). Demo only and
  labelled as simulated.
- **Read-only after confirming:** changing a confirmed request (refining the window during negotiation) comes
  with M6 and M7.
- **Not tested:** real phone cameras, microphones and native date pickers.

## M4 Worker onboarding and identity check — complete (27 Nov 2026)

### Delivered

- [x] **Three-screen worker onboarding:**
  - Screen 1 is signup, with worker preselected from "مجھے کام چاہیے" and a play button for the fixed
    password instruction.
  - Screen 2 is trade, services and one main speciality, with exclusions under "More options".
  - Screen 3 is a city plus travel areas.
  - Saved per screen, with resume after a refresh or login. Urdu RTL and English.
  - No microphone, location or CNIC needed.
- [x] **Server-side validation** reuses the catalog rules: cross-trade services, main speciality not offered,
  offered/excluded overlap, areas outside the city.
- [x] **Worker dashboard:** eligibility with reasons, identity status, profile summary and edit links, the
  accepting-requests choice (separate), phone confirmation, and an optional voice introduction link.
- [x] **Real CNIC OCR:** Tesseract on the host.
  - Images are validated before OCR (type, ≤ 5 MB, ≥ 400 × 250 px, ≤ 40 MP).
  - Orientation, contrast and size are normalised, with up to four rotations within a 20 s budget.
  - The temp folder is deleted and the image is not stored.
  - Only the name and number are extracted; raw text is never logged or returned.
- [x] **Editable review** of both fields (original scan shown, edits marked as corrections), retake, and
  typing after an unreadable scan.
- [x] **Simulated registry only:** name and number must match the same fictional record; `match`,
  `name_mismatch` and `no_record` states; a labelled demo address; demo-only (startup guard, runtime guard,
  seed refuses live).
- [x] **Recorded per attempt:** status, method, timestamps, masked number, keyed digest, registry reference and
  correction flags.
- [x] **Shared `worker_eligibility()`** for M6 and M8 (see architecture §10); demo approval counts only in demo mode.
- [x] **Read-only staff admin** for verification status and its source; the demo registry is visible.
- [x] **Customer signup:** one screen, customer preselected from "مجھے کاریگر چاہیے", then the customer dashboard.
- [x] **Fixed-instruction speech endpoint:** keys only, cached.
- [x] **`check_ai_providers --only cnic_ocr --cnic-image …`** for real OCR checks.
- [x] **Synthetic DEMO cards** in `docs/demo/cnic/`, plus the `seed_demo_registry` command.

### Real OCR results (actual `tesseract.exe` v5.4.0.20240606, Windows, `eng`), 27 Nov 2026

| Sample (pixels only, no embedded data) | Result |
|---|---|
| `demo-card-bilal-ahmed.png` 856×546 | read: `Bilal Ahmed`, `00000-1234567-1`, 0.4 s |
| `demo-card-sana-tariq.png` | read: `Sana Tariq`, `00000-7654321-2` |
| `demo-card-imran-siddiqui.png` | read: `Imran Siddiqui`, `00000-2468135-3` |
| `demo-card-wrong-name.png` | read: `Kamran Shah`, `00000-1234567-1` |
| `demo-card-unknown-number.png` | read: `Usman Ali`, `00000-9999999-9` |
| `demo-card-sana-tariq-rotated.jpg` (sideways retake, 626×936) | read after turning 270°: `Sana Tariq`, `00000-7654321-2`, about 1.5 s |
| `demo-card-imran-siddiqui-lowquality.jpg` (470×300, blurred, low contrast, JPEG q35) | **partial**: number `00000-2468135-3` read; the "Name" label was garbled, so the name was left blank (by design: no guessing) |
| `demo-card-unreadable.jpg` (heavy blur) | unreadable: both fields blank |

The first real run exposed a bug in choosing the best rotation: the status strings were compared
alphabetically, so the rotated card came back "unreadable". It is now fixed with an explicit ranking, and the
rotated card is read.

### Browser walk-through (real backend, real Tesseract, Chrome at 360 px), 27 Nov 2026

1. **Urdu worker journey (UI only):**
   - "مجھے کام چاہیے" → signup with worker preselected, "Step 1 of 3" and the listen button.
   - Screen 2: electrician, fan installation and wiring, main speciality fan installation, UPS excluded.
   - Screen 3, after a **page refresh**, resumed correctly: Islamabad, G-9 and G-10.
   - Dashboard: "Not yet", "Verify your identity", the verify button and the phone prompt.
   - Verify: consent → upload the Bilal card → real OCR filled `Bilal Ahmed` / `00000-1234567-1` (0.5 s) → submit
     → the exact passed message and the labelled demo address → the dashboard said "Yes, you can take jobs".
   - No horizontal overflow on any screen.
2. **Wrong name:** the scan read `Kamran Shah` → "name does not match" → the name was corrected to
   `Bilal Ahmed` → passed, with `name_corrected: true`.
3. **Unknown number:** the scan read `Usman Ali` / `00000-9999999-9` → "No demo record found".
4. **Unreadable photo:** "nothing could be read" with both fields empty.
   - Retake with the rotated card: read (rotation 270).
   - Retake with the low-quality card: partial; the typed name plus the scanned number passed
     (`name_corrected: true`).
5. **New login:** after saving screen 2, logging out and logging in again landed on `/worker/setup/areas`.
6. **Customer:** "مجھے کاریگر چاہیے" → customer preselected → `/customer`, with phone confirmation there.
7. **Live mode on the real database:** the worker approved in step 1 is eligible in demo mode. With
   `APP_DEPLOYMENT_MODE=live` the same worker gets `can_take_jobs: false`, reason
   `demo_approval_not_accepted_here`. `IDENTITY_VERIFICATION_PROVIDER=demo_registry` with live mode is
   refused at startup.

The walk-through found and fixed:
- The Urdu number example (`12345-1234567-1`) displayed in reverse group order inside RTL text; it is now
  wrapped in LTR isolate marks.
- The success title duplicated the message.

### Automated checks (mocked where noted)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **233 passed**: onboarding rules, resume, eligibility, identity flow with a stub OCR, image validation, live-mode rejection, ownership, admin, seed, startup guard, instruction audio, Tesseract adapter with mocked `subprocess`, and **3 tests that run the real Tesseract executable** on the cards (skipped automatically if it is not installed) |
| `check`, `makemigrations --check` | ✅ No issues; `workers.0001`, `voice.0002` |
| Frontend typecheck / tests / build | ✅ No errors / **61 passed** (mocked API) / built |

Also fixed during M4:
- `IconTileGroup` multi-select groups were announced twice by screen readers (a fieldset plus a duplicate
  `role=group`).
- The catalog API always reported `"multiple": true`.

### Known limitations

- **Card design:** OCR is tuned and verified on the synthetic DEMO cards only (printed English name and number
  on a plain background). Real CNIC photos, Urdu names and the back of the card are not tested. Low-quality
  photos may yield only the number.
- **Phone cameras:** "Take a photo" uses the browser's file picker with `capture`. Physical phones are not
  tested.
- **Scope:** no staff manual-review workflow yet (read-only admin); the eligibility check is defined but only
  M6 and M8 will call it.

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
- **Live check (26 Nov 2026, with the developer's keys)**:
  - ElevenLabs `eleven_v3` + premade voice George (`JBFqnCBsd6RMkjVDRZzb`): `[OK]`, real Urdu MP3 (122 KB) for a
    fictional sentence. A Voice Library voice failed with `402 paid_plan_required` (free plan) — now reported as
    `ai_provider_not_configured (paid_plan_required)`; a pasted key *ID* (`api_key_id_used_as_api_key`) is
    reported as `credentials_rejected`.
  - Gemini, with that MP3 as the speech sample: `gemini-3.6-flash` and `gemini-3-flash-preview` `[OK]` —
    transcript `میرا نام احمد ہے۔ میں electrician ہوں۔ میں پنکھے لگاتا ہوں لیکن motor rewinding نہیں کرتا۔`;
    draft trade `electrician`, offered `elec_fan_install`, "motor rewinding نہیں کرتا" unmatched and **negated**.
    `gemini-3.8-flash` / `3.7-flash` answered `503` "high demand" all morning (Google-side, temporary).
  - Confirmed the real Interactions response shape: top-level `steps` (no `output_text`); the adapter's
    `steps[].model_output` path handled it.
- **Fixed**: the test settings inherited providers and keys from the developer's `.env`, so with real keys the
  suite called Gemini/ElevenLabs. `config/settings/test.py` now forces fixtures and blank keys, with a regression
  test. Backend **187 passed** with the real `.env` present.
- Not yet verified: listening quality of the Urdu voice (by a person), the in-browser flow with live providers.

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
