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
| M7 Communication and agreements | ✅ Complete (27 Nov 2026) — fixture walk-through; live Gemini agreement check verified with `gemini-3-flash-preview` |
| M8 Booking and arrival | ✅ Complete (27 Nov 2026) — two-session walk-through with fixture AI; PostgreSQL concurrency tests |
| M9 Completion and feedback | ✅ Complete (27 Nov 2026) — Urdu two-session walk-through with fixture AI; PostgreSQL race tests |
| M10 Reporting and moderation | ✅ Complete (27 Nov 2026) — Urdu report through staff resolution; separate customer, worker and staff sessions |
| Pitch improvements (ElevenLabs + Groq, voice signup, demo verification, Urdu descriptions) | ✅ Implemented (27 Nov 2026). Groq live-checked 28 Nov; Scribe Urdu needs the `scribe_v2` fallback |
| Theme and UX pass (Kaam Madad theme, navigation, next steps, quote summary) | ✅ Implemented (28 Nov 2026); live two-role rehearsal in the app |
| UX redesign (full-width screens, job stages, quote screen, work progress, no demo branding) | ✅ Implemented (28 Nov 2026); tests and build pass; browser check below |
| M11 Integration and delivery | ⬜ Next |

---

## UX redesign — implemented (28 Nov 2026)

Frontend only. The backend APIs, permissions and workflow rules are unchanged and remain the source of truth.

### Delivered

- **Full-width workspace:** the route-level narrow/medium/wide caps are gone. Every page uses the width beside the
  sidebar, with normal gutters. Prose and input groups keep comfortable line lengths. Desktop uses natural columns:
  - login beside the two ways to sign up;
  - signup fields in two columns;
  - request details: what and where | when, private address, budget and photos;
  - review: summary | what the worker receives;
  - invitation, saved request, chat, quote and booking: content | next action.
- Choice tiles are smaller and use 3–4 columns on wider screens.
- **New request, screen 1:** a short heading and one compact step bar ("Step 1 of 3" is kept for screen readers).
  - Compact Speak / Type and اردو / English toggles. The input language follows the interface language until the
    customer picks one.
  - Recording, upload, Continue, retry and the manual path are unchanged.
  - Typed text, the recording and an already-created draft are kept in memory across mode and language switches and
    visits to other screens, so nothing is created twice.
- **Job stages:** `JobStages` (Request & chat → Quote → Work progress) appears on all three screens for both roles. It
  is built from the invitation header, the quote listing (readiness, version, draft) and the booking. Each step shows
  its status and links to its own screen; Work progress becomes a link once a booking exists.
- **Request & chat** (`/conversations/:id`, unchanged URL):
  - The thread and composer, a compact request summary (with Listen and "View request details"), and the next action:
    - worker: "Prepare a quote", or "Continue your draft";
    - customer: one short waiting status, or "View quote" with the version, total and ready / not-ready;
    - booked: "Open work progress".
  - Report and block stay beside the chat.
  - The quote form, terms, check panel and acceptance are no longer on this screen at any width.
  - The thread scrolls on its own on desktop, so the composer stays in view.
- **Quote** (`/conversations/:id/quote`, new): reuses `QuotePanel`, `QuoteForm` and `AcceptQuote`.
  - Total, materials, scope and appointment come first.
  - The next-action card holds readiness and the open findings, with their sources behind "Show where this comes from".
    It also holds retry / manual review, accept (customer), revise (worker) and "Back to chat".
  - Full terms, clarified points and earlier versions are behind details.
  - The worker writes at `?edit=1`, next to the customer's request. Unsent quote terms survive a visit to the chat.
  - Server readiness, versions, idempotent acceptance and stale-quote handling are unchanged.
- **Shared layout:** the chat and quote screens share one layout route. The header, catalog and the single quote poll
  load once, so switching screens adds no requests.
- **Work progress** (`/bookings/:id`):
  - Acceptance still opens it directly.
  - The real status comes first ("Booked", then "In progress" …) with this person's next step.
  - Arrival, code, start, completion and review panels follow. A pending change needing a decision stays in view.
  - Time, address, price, chat link, report/block and cancel are in the side column.
  - Agreed terms, change history, past events and the request are behind details.
- **Links to stages:**
  - A booked request on the customer dashboard and a booked invitation in the worker inbox open Work progress
    directly.
  - Request cards show one status.
- **Demo and developer information removed** from normal screens:
  - the header demo badge and banner, dashboard demo-account badges, and the landing "early version" notice;
  - the landing server-status card, and the dashboard Voice Test link.
  - "Demo" wording stays on the identity-verification screens only.
  - Phone codes: "No SMS is sent. Your code will be shown on this screen." / "Your code is shown below".
  - Simulated identity elsewhere reads "Sample check only (not an ID check)".
  - `/diagnostics` (unlinked) shows readiness and provider configuration for developers.
- **Phones:** the bottom bar steps aside while a text field has focus, so it cannot cover the composer or form buttons
  above the keyboard.

### Automated checks

- `npm run build` (typecheck + Vite build) passes.
- `npx vitest run --maxWorkers=2`: 19 files, 124 tests pass.
  - New tests: stage header and links; the customer's waiting status with no quote panel on the chat screen; chat →
    View quote with no chat thread and no extra header request; Back to chat keeps the unsent message.
  - Also new: a direct quote link fetches no messages; Prepare quote → `?edit=1` → send returns to the quote view;
    quote terms survive a visit to the chat; accept → Work progress "Booked" with stage links.
  - Also new: worker "In progress" next step; new-request language default and drafts; dashboard stage links; no
    demo branding on the landing page, header or dashboard; `/diagnostics`.
- `vitest.config.ts` now sets `testTimeout: 20000`. At HEAD, 3 tests (completion, theme, voice test page) already
  failed with the 5 s default timeout on this 18-core / 7.5 GB machine, and passed when run alone.

### Browser walkthrough (28 Nov 2026)

- **Setup:** real Django + PostgreSQL (5434) with fixture AI providers (process environment only), Vite dev server,
  and headless Microsoft Edge driven by Playwright.
- **Data:** fictional accounts only. One customer per run (`0300777xxxx`) and one demo-approved worker per run
  (`0300888xxxx`, created the way `seed_demo_workers` does).
- **Languages:** customer in English (LTR), worker in Urdu (RTL); the Urdu customer screens were checked at the end.
- **Result:** 55 checks passed.
  - Landing page: no demo text and no server status.
  - New request: the input language defaults to the interface language (English, then Urdu); typed text survives a
    mode switch.
  - Worker chat: "Prepare a quote", with no quote form, terms or accept. A message was sent from the Urdu composer.
  - Prepare quote → `?edit=1`, with the request beside the form and no chat thread. Version 1 (customer brings
    materials) was blocked by the materials check. The customer saw "View quote" in the chat; the quote screen had the
    total first and no thread.
  - Back from quote → chat.
  - Revision to version 2 (materials included) → the customer accepted → Work progress showed "Booked", with the stage
    header on Work progress.
  - Back → the quote showed "Quote accepted" with "Open work progress". The worker inbox linked straight to the
    booking.
  - The worker's "I have arrived", then the customer's code, gave "In progress" for both roles.
  - Direct links and refresh worked for the quote, the chat and the old conversation URL.
- **Widths (360, 390 and 1440 px):** no horizontal scroll. With a text field focused at 390 and 360 px, the bottom bar
  was hidden and the primary button was inside the viewport.
- **Not verified:** a real on-screen keyboard (headless browser; the check relies on the bottom bar hiding on focus
  and the button fitting), and voice recording in the browser.

---

## Theme and UX pass — implemented (28 Nov 2026)

Visual reference: the Kaam Madad theme ZIP (`frontend/Kaam-Madad-Frontend.zip`). It is used only as a reference and
is never committed or built. It is ignored in `.gitignore`, and none of its JavaScript is copied. From it, the app
reuses the palette, the electrician hero photo (`src/assets/hero-electrician.webp`), the brand mark, and the Noto Naskh
Arabic body font (OFL, `src/assets/fonts/`). The Noto Nastaliq Urdu display font comes from the existing `@fontsource`
package.

### Delivered

- **Theme:** navy/indigo with warm gold; Naskh for Urdu body text and labels (legible on small screens); Nastaliq for
  the brand and hero headings. White cards, and "action" cards with a gold edge.
  - Form-control borders keep at least 3:1 contrast.
  - The focus ring is a visible 3 px indigo ring, gold on dark surfaces.
- **Shell:**
  - Desktop: a role-aware sidebar.
  - Phones: a four-item bottom bar using real routes or dashboard sections (`/worker#invitations`, `#bookings`,
    `/customer#requests`, and so on). The main content leaves room above the bar.
  - Every screen: the language switch, the demo label and log out stay in the top bar.
  - Page width per route: task forms stay narrow; dashboards and the conversation are wide.
- **Landing and dashboards:**
  - "مجھے کام چاہیے" and "مجھے کاریگر چاہیے" are the entry points.
  - Each dashboard shows a "next step" computed from real state: bookings, verification, invitations, the accepting
    switch, drafts and confirmed requests.
  - There are no sample people, ratings or counters. The outdated "not available yet" texts are gone.
- **Worker signup:** still three steps followed by demo verification. "Answer by voice" sits beside the manual tiles,
  with numbered steps (record → write down → check), a live status, and "try again" keeping the recording. "Listen to
  my choices" is on step 3.
- **Customer request:**
  - Speak and Type are equal tiles.
  - Text and choices survive a language switch (tested).
  - The review step shows "What the worker will receive" (the approved Urdu version, or the original marked with its
    language).
- **Worker invitation:** the task, area, time and Listen control are in one card above the next action.
  - `SharedJob.tsx` now reads an original Urdu description in Urdu playback when there is no approved translation.
  - Approved Urdu is still preferred, and the structured-only fallback remains for untranslated English (regression
    tests in `SharedJob.test.ts`).
- **Quote and agreement:**
  - Desktop: the chat beside the quote panel.
  - Phones: a summary above the chat (known total, who supplies materials, blocking issues) linking to the full quote.
  - The real check status, sources, clarification, revision, manual review and accept safeguards are unchanged.
- **Booking, arrival, completion, review and reports:** same card and header treatment.
- **Groq agreement check, after live runs:**
  - A glossary of the coded quote terms and finding codes.
  - Messages are numbered, and the instruction says to judge by each person's latest statement.
  - High reasoning effort, with one retry at medium after a Groq schema rejection.
  - Temperature 0.2.
  - Completion budgets of 2500 for interpretation and 3500 for the agreement check: the free tier counts the requested
    maximum against 8000 tokens per minute.
  - `check_ai_providers` waits for rate limits.

### Checks (28 Nov 2026)

| Check | Result |
|---|---|
| Frontend typecheck / tests / build | ✅ No errors / **117 passed** (10 new: navigation, next step, language switch keeps input, quote summary, SharedJob playback; async test timeout raised to 3 s for cold runs) / built; `dist` holds no reference-ZIP files |
| Backend suite | ✅ **409 tests** OK (new: Groq glossary/order and effort fallback) |
| Layout audit in real Chrome (headless, DevTools protocol) | ✅ Guest pages at 360/390/1280 px in Urdu and English, plus 30 signed-in page/width checks. No horizontal overflow, every control labelled, the last action never under the bottom bar, focus ring visible |

### Live-provider results (fictional data) vs fixtures

| Step | Provider | Result |
|---|---|---|
| `check_ai_providers --only interpretation` | **Live Groq** | ✅ All four: English job → Urdu description with AC service negated, G-9; signup work (UPS negated) and areas (F-8 excluded). 1.4–2.0 s |
| `check_ai_providers --only agreement_check` | **Live Groq** | ✅ Urdu sample, pitch v1 (one materials finding), pitch v2 revised (no findings), Roman Urdu; the timing case passed (materials + timing) when spaced. Before the glossary and ordering: v2 gave a false positive. Repeated runs at high effort: v2 6/6 clean, v1 3/3 |
| Browser rehearsal, worker voice answer (screen 2) | **Live ElevenLabs Scribe** (v3 → v2 Urdu fallback) + **live Groq** | ✅ Fan installation and wiring offered, UPS "not offered" (negation), filled as editable tiles |
| Silent clip on screen 3 | Live Scribe | ✅ "No words heard" failure state; recording kept; manual tiles used |
| Listen to my choices; Urdu invitation read-aloud | **Live ElevenLabs** `eleven_v3` | ✅ HTTP 201 audio |
| English request → Urdu description → worker | **Live Groq** | ✅ Original kept, Urdu suggested, approved by the customer, and shown first to the Urdu worker |
| Quote v1 labour only → clarification → v2 with materials | **Live Groq** agreement check | ✅ v1: exactly one materials finding with sources. v2: `passed`, `simulated=False`, no manual review. Then accepted → booking |
| Unit and component tests | Fixtures / mocked HTTP | As above |

### Notes

- Headless full-page screenshots draw fixed elements (header, sidebar, bottom bar) part-way down. That is an artifact
  of capturing beyond the viewport, not the layout.
- Before the rehearsal, the dev machine had a stale second `runserver` on port 8000 from an earlier session, which
  made one run stall. Only one server should listen on 8000.
- Still to check by a person: real phones (microphone, camera, native pickers) and the listening quality of Urdu
  speech.

---

## Pitch improvements — implemented (27 Nov 2026)

These changes prepare the event demo. They do not replace M11. Setup and rehearsal are in the
[README](../README.md#pitch-configuration-and-rehearsal-hackathon).

### Delivered

1. **Providers**
   - Speech-to-text: ElevenLabs Scribe (`scribe_v3`) for recorded or uploaded clips. It reuses `ELEVENLABS_API_KEY`
     and the existing upload checks and permissions. Report and dispute audio stays outside the pipeline.
   - Text AI: Groq (`openai/gpt-oss-120b`, configurable) for interpretation and the agreement check.
     - Groq is asked for strict JSON Schema output (all properties required, `additionalProperties: false`).
     - The output is still validated by `apps.voice.drafts` and `verify_findings`.
     - Groq errors map onto the existing error types: 429 and 498 are usage limits, timeouts and 5xx are retried
       within the bounded budget, and a truncated or non-JSON answer is invalid output.
   - Wired into settings, `providers/registry.py`, `.env.example`, `GET /config/` and `check_ai_providers`.
     Gemini stays selectable.
2. **Worker signup in three steps**
   - Screens 2 and 3 offer **Answer by voice**: Scribe transcribes, then Groq suggests catalog choices for that
     screen only (new interpretation kinds `onboarding_work` and `onboarding_areas`).
   - Negation is respected, and ambiguous choices are left unselected: a main speciality that isn't clear or isn't
     offered, areas in two cities, or the same thing said both ways.
   - Suggestions fill the normal editable tiles; nothing is saved until the worker saves. Manual selection keeps
     working when voice or AI fails.
   - Screen 3 has **Listen to my choices**, built from the actual selections and localized catalog labels.
3. **Demo verification**
   - `POST /api/v1/identity/demo-verification/` takes a sample CNIC and a sample selfie. They are validated with
     the existing image limits, then the existing `demo_approved` status is recorded with the new method
     `demo_sample_upload`.
   - No OCR, extraction, face matching or registry lookup. Nothing is retained (metadata only) and nothing is sent
     to a provider.
   - Refused outside demo mode (403 `demo_verification_unavailable`). Existing records are kept: an already
     approved worker gets 409, and a suspension is not bypassed.
   - Fictional samples: `frontend/public/demo-samples/` (the demo card, plus an illustrated selfie labelled "not a
     real person").
   - `/worker/verify` is now the two-upload screen; the M4 scan is at `/worker/verify/card`. After screen 3 the
     worker is offered verification and can choose "Do this later".
4. **English requests for an Urdu-speaking worker**
   - The customer's own words now stay the description for typed and spoken English, Roman Urdu or mixed input.
     This fixes the typed-English prefill in `jobs/views.py`.
   - The same interpretation call's faithful Urdu wording is stored as a *suggested* `description_ur`. The customer
     reviews, edits and approves it on the details screen, or before inviting.
   - Only an approved version that matches the current description is shared
     (`matching_summary.description_ur`, plus `description_language`).
   - Changing the description marks a pending or approved Urdu version **outdated**.
   - The worker's Urdu view shows the approved Urdu description first and the original marked with its language.
     Read-aloud includes the approved Urdu description with the services, area, date and time.
   - Without interpretation, manual submission still works: the worker sees the localized structured details and
     the original notes marked as English.
5. **Agreement check through Groq** in the real quote workflow. It uses the current findings format, verified
   sources, authorized inputs (now also the approved Urdu description) and the quote-version checks.
   - The instruction includes the merge rule verbatim. Same-code findings are also merged in code.
   - The question follows the conversation language (Urdu script, Roman Urdu or English).
   - Later statements and the quote supersede earlier ones.
   - An ungrounded answer (findings that can't be traced to the input) is refused as `findings_ungrounded`, shown
     as "could not run".
   - An AI timing finding is not repeated when the deterministic time rule already asks.
   - The fixture's materials rule now treats a quote that includes the materials the customer asked for as
     settled.
6. **Ranking unchanged:** the AI only suggests the request's tags, the customer confirms them, and the existing
   matcher ranks.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend `check`, `makemigrations --check` | ✅ No issues; migrations `jobs 0002`, `voice 0006`, `workers 0002` added |
| Backend suite (real PostgreSQL, fixtures and mocked HTTP) | ✅ **407 tests** OK (54 new for the pitch; 3 existing assertions updated for the new summary keys and command output) |
| Frontend typecheck / tests / build | ✅ No errors / **107 passed** (8 new) / built (existing chunk-size warning) |
| Pitch example through the real quote workflow | ✅ Fixture and mocked Groq: Rs. 1,200 "including materials" vs labour only → exactly one materials finding; revision with materials included → no findings and ready; Roman Urdu → one finding with a Roman Urdu question; timing outside the request → a second, separate finding |
| Failure never shown as a clean check | ✅ Groq 429, timeout, ungrounded and truncated answers → "could not run" with no AI findings; manual review still works; a late result for a superseded version is discarded |
| Demo verification | ✅ Sample images approved in demo mode without OCR or registry; refused in live mode; approval does not count in live mode; existing approval and suspension kept |
| Manual paths | ✅ Onboarding saves with STT and AI unconfigured; English request completed and shared without interpretation |
| Ranking | ✅ AI-suggested G-9 ceiling fan request: fan specialist `03009990101` first, paused `03009990104` excluded, same order on repeat |

### Live provider checks (this machine, fictional data; separate from the fixture tests above)

| Provider | How | Result |
|---|---|---|
| ElevenLabs `eleven_v3` read-aloud | `check_ai_providers --only text_to_speech` (Urdu with English terms, then English) | ✅ MP3 returned for both (`simulated=False`) |
| ElevenLabs Scribe `scribe_v3`, English | Transcribed the English clip above, with the `en` and `auto` hints | ✅ "Please install two ceiling fans in G9 tomorrow evening. No AC service needed." (about 5 s); negation kept, "G-9" written as "G9" |
| ElevenLabs Scribe `scribe_v3`, Urdu | Transcribed the Urdu clip, with `language_code` `ur`, `urd`, auto, and `urd` + secondary English | ❌ Every variant returned **Devanagari** (Hindi script), with the words and English terms correct. The adapter refused it as `transcript_wrong_script` |
| ElevenLabs Scribe `scribe_v2` and `scribe_v1`, Urdu | Same clip | `scribe_v2` + `ur` ✅ Urdu script ("میں electrician ہوں۔ … لیکن UPS کا کام نہیں کرتا۔", one small word error: لگتا for لگاتا). `scribe_v1` ❌ Devanagari. With auto-detect, all three returned Devanagari |
| Scribe adapter with the Urdu fallback | `check_ai_providers --only speech_to_text --language ur` | ✅ `elevenlabs/scribe_v2` Urdu script, `language=mixed`, 7.4 s in total (v3 call + fallback) |
| Groq (interpretation, agreement check) | `check_ai_providers` with `INTERPRETATION_PROVIDER=groq AGREEMENT_CHECK_PROVIDER=groq` | ⏳ Not run live: no `GROQ_API_KEY` in `.env` (`ai_provider_not_configured (missing_api_key)`) |
| Gemini interpretation (still selectable; `.env` default) | `check_ai_providers --only interpretation` | ✅ Worker introduction, signup work (UPS negated, main = fans) and areas (G-9, G-10; F-8 excluded) on `gemini-3.6-flash`, 5–8 s each. ❌ English job description: timeout twice (20 s), as seen before with this model |

### Rehearsal (API, real Django stack, dev database, fictional accounts)

A scripted rehearsal ran in-process through the real views on the dev database:
- Live ElevenLabs for speech-to-text and read-aloud. Fixture interpretation and agreement check (no Groq key).
- No browser was available, so screens were exercised by the frontend tests instead.

All 18 steps passed:

1. Worker signup (screen 1).
2. Voice answer on screen 2: the live Scribe transcript came from `scribe_v2` after the v3 Devanagari result, in 3.0 s.
   The fixture's suggestions kept UPS as "not offered".
   - It missed fan installation because Scribe heard "لگتا" for "لگاتا". The worker added it on screen, as the UI
     allows.
3. Screens 2 and 3 saved.
4. Live Urdu "Listen to my choices".
5. Demo verification with the sample images. The worker can then take jobs.
6. Customer signup (one screen).
7. Spoken English request: live Scribe v3 transcript kept as the description, with an Urdu version suggested.
8. Typed English request: description kept; catalog tags and an Urdu version suggested.
9. The customer approves the Urdu description and confirms the request.
10. Ranking: the same order twice and the paused worker excluded.
    - The dev database also has three earlier fictional G-9 fan specialists. They tie with `03009990101`, which is
      third here.
    - The seeded-only case (specialist first) is covered by the automated test.
    - For the pitch, use a database with only the seeded demo workers, or expect those extra fictional workers.
11. The worker sees the approved Urdu description, with the original marked English and no address.
12. Live Urdu read-aloud, 354 KB. A repeat was served from the per-owner cache in 0.4 s.
13. Quote v1, labour only: exactly one materials finding.
14. Clarification recorded, then the revised quote: no findings, ready for acceptance.

The invitation was withdrawn afterwards. The fictional rehearsal accounts remain in the dev database.

### Still needs a live check

- **Groq:** run `check_ai_providers --only interpretation` and `--only agreement_check` with a `GROQ_API_KEY`.
  This covers the English → Urdu description quality, the onboarding suggestions, and the four agreement scenarios
  (exactly one materials finding, none after revision, Roman Urdu, materials + timing).
- **Rehearsal:** the browser rehearsal in the README with the live providers, on real phones (microphone and
  camera).
- **Scribe on real Urdu voices:** the fallback was verified on one synthetic Urdu clip. Real speakers and accents,
  and whether a future `scribe_v3` update writes Urdu script, still need checking.
- **Speed:** the agreement check still runs inside the request. Groq's speed was not measured live.

### Known limitations

- **Simulated Urdu:** the fixture's "Urdu description" is assembled from catalog labels. It is not a translation and
  is labelled simulated.
- **One clarification:** the Urdu description is one free-text field. Conversation messages are still not
  translated.
- **Dead links:** the old M4 OCR page stays available, but nothing links to it.

---


## M10 Misconduct reporting and moderation — complete (27 Nov 2026)

### Delivered

- [x] **Private reports:**
  - "Report a concern" on the conversation and booking screens, for customers and workers, including after
    the interaction closes. Restricted accounts can report too.
  - The reported person is derived on the server, so a client can neither pick an unrelated account nor report
    itself; a database check also forbids self-reports.
  - Six categories. A typed description or a voice note is required. Up to 5 evidence images are re-encoded
    without metadata; audio evidence works with no transcription.
  - Report audio is refused by the transcription endpoint, and report text and files are never logged or sent
    to providers.
  - Filing is retry-safe (`client_id`) and changes no booking or account.
- [x] **"My reports":**
  - statuses open, reviewing, resolved and dismissed;
  - staff messages meant for the reporter, with a reply box when staff ask for information;
  - the reporter's own evidence, downloadable only by them;
  - the reported person and third accounts get 404 everywhere.
- [x] **Django Admin queue:**
  - filters by status, category, awaiting reply and date; links to the invitation and booking;
  - **Record a decision…** (mark reviewing, ask for information, resolve, dismiss, internal note), with a
    required reason and a reporter-visible message kept separate from internal notes;
  - three explicit permissions (`review_report`, `view_evidence`, `take_account_action`);
  - every decision is audited with actor, time and old/new state, and every evidence opening is recorded.
- [x] **Restriction (separate from suspension):**
  - `User.restricted_at` blocks new requests, invitations, messages, quotes and bookings on the server.
  - Restricted workers drop out of recommendations, invitations and booking readiness.
  - Restricted users keep sign-in, their records, existing bookings (M8/M9), reports and replies.
  - Suspension stays `is_active=False`. Lifting and reactivation are audited actions too.
- [x] **Blocking:**
  - "Block further contact" stops new messages, quotes, invitations and bookings between the pair in both
    directions, and hides the worker from that customer's recommendations.
  - History, reports, evidence and existing bookings are kept, and M8/M9 booking actions stay available.
  - Only the blocker can lift it, and the other side is not told who blocked.
- [x] **Retention:** `purge_report_evidence` removes evidence content of reports closed more than 180 days
  (configurable). It never touches open cases or active disputes, keeps the audit trail, and prints counts only.
- [x] **Dashboards:** a restriction notice and a "My reports" link for both roles.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **353 passed** (16 new for M10) |
| `check`, `makemigrations --check`, `migrate` | ✅ No issues; migrations `accounts.0003`, `voice.0005`, `reports.0001` applied |
| Frontend typecheck / tests / build | ✅ No errors / **99 passed** (5 new) / built |

Backend tests cover:
- **Filing:**
  - both roles can report, the reported person is derived, and retries are safe;
  - a voice note alone is enough, and `reported_id` is rejected as an unexpected field;
  - strangers get 404;
  - reporting works after withdrawal, a report on an in-progress booking leaves its status and events untouched,
    and M9 completion still works;
  - report audio is not transcribable.
- **Privacy:**
  - the reported person and a third account get 404 on the report, evidence, replies and list;
  - the conversation header never mentions reports;
  - report text is not logged;
  - evidence limits (bad image → 415, a 6th item → 409, another user's clip refused).
- **Staff:**
  - without the review permission, decisions are refused;
  - ask for information → the reporter sees only the staff message (not the internal note) → reply → resolve →
    no replies after closing;
  - the audit has old/new state and the actor.
- **Admin permissions:** the queue and decide views give 403 without `review_report`. Evidence gives 403 without
  `view_evidence` and leaves no access record; with it, one access is recorded.
- **Account actions:** they need `take_account_action`; the audit has old/new state; the report text is
  unchanged; lifting works; suspension logs the session out.
- **A restricted worker:**
  - cannot message (403);
  - can read, report and reply;
  - is not recommended, and booking from an existing quote fails with `worker_not_eligible`;
  - the existing booking's completion and confirmation still work.
- **A restricted customer:** cannot create requests, invite or accept (403). They can reply to staff, `me` shows
  `restricted`, and booking works again after the restriction is lifted.
- **Blocks:**
  - messages both ways → 409, while history is kept;
  - `by_me` is attributed correctly;
  - no new invitation and no recommendation for the pair;
  - only the blocker can unblock;
  - a block during a booking keeps completion and dispute working.
- **Retention:** old closed evidence content is removed (file and clip deleted, report kept, `removed` shown).
  Open reports and reports on disputed bookings are preserved.

### Walk-through (Urdu at 360 px for the customer and worker; Django Admin at desktop width for staff)

The walk-through used a fictional rehearsal worker (03009990195, paused afterwards) and fictional staff:
moderator 03009990900, and reviewer 03009990901 without `view_evidence`. Fixture AI was used.

1. **Setup:** the worker sent a threatening message in the conversation. A second booking was taken to In
   progress.
2. **Report:** the customer opened **شکایت درج کریں** from the conversation, chose **دھمکیاں**, described it in
   Urdu, attached a photo and sent it. The report page showed "کھلی".
3. **Privacy:** the reported worker got 404 on the report and its evidence, and saw 0 reports in their list.
   The booking stayed `in_progress`.
4. **Staff:**
   - The reviewer opening the evidence got **403**, with no access recorded.
   - The moderator used the queue filtered by open/threats, opened the evidence (**200**, recorded), and chose
     **Ask the reporter for more information** with an Urdu message and an internal note.
5. **Reply:** the customer saw "عملے نے مزید معلومات مانگی ہیں" and the staff message. The internal note was not
   visible. The customer replied in Urdu.
6. **Block:** the customer tapped **مزید رابطہ بند کریں** and confirmed. A worker message then returned
   `409 contact_blocked`, and the one earlier message was still in the history.
7. **Resolution:** the moderator resolved the report with an Urdu message and **Restrict the reported account**
   with a reason.
   - The audit shows request_info, resolve and restrict with old/new state.
   - The customer saw "حل شدہ" with the staff message.
8. **Restricted worker:**
   - The dashboard showed **آپ کا اکاؤنٹ محدود ہے** and the eligibility reason.
   - A message → `403 account_restricted`; filing their own report → `201`.
   - On the existing booking, requesting completion → `200`, and the customer's confirmation → `completed`.
9. **Layouts:** no horizontal overflow on the customer and worker screens. The Admin audit page is wide at
   desktop width (Django's own tables).

### Known limitations

- **No notifications:** the reporter sees staff updates only when opening "My reports".
- **Evidence types:** evidence is images and audio only (no documents or video). A reply is text only.
- **Admin tooling:** the decision form is a minimal Admin view. There is no assignment, SLA or bulk action.
- **Appeals:** the reported person is not notified of reports or decisions, other than seeing a restriction
  notice; there is no appeal flow.
- **Retention is manual:** the retention command is not scheduled yet (M11).
- **Image error wording:** the existing image error messages mention "the card" (from M4).
- **Leftover data:** fictional rehearsal workers 03009990195–0199 and staff 03009990900/0901 remain in the
  development database.

### Next module

**M11 Integration and delivery:** deployment configuration, scheduled retention, staff groups, and final
end-to-end checks and submission materials.

---

## M9 Completion, disputes and feedback — complete (27 Nov 2026)

### Delivered

- [x] **Completion:**
  - The worker asks the customer to confirm, from `in_progress`. It is refused while a change is pending
    (`change_open`), and the UI explains why.
  - The customer confirms → `completed`: the reservation is released, and the booked catalog services are
    recorded as completed.
  - Or the customer raises an issue (reason and note) → `disputed`.
  - The worker can never complete alone, and the booking stays pending until the customer answers.
  - Every action is atomic and retry-safe with the M8 lock order. There are no duplicate events, and only one of
    confirm or dispute can win.
- [x] **Reservations:** `completion_requested` and `disputed` keep the reservation and count as the worker's
  current job. The exclusion constraint, the one-started-job constraint and the start check were all extended,
  so a second start is refused even after the planned end.
- [x] **Terms freeze** while completion or a dispute is pending. The accepted snapshot, the change history and the
  worker's accepting-requests preference are untouched.
- [x] **Django Admin** (permission-checked): **Record dispute outcome**, either return to in progress or close
  without confirmed completion, with a reason. Closing releases the worker, closes the invitation, never
  unlocks a review and gives no work credit.
- [x] **One review per completed booking:**
  - 1–5 stars, an optional short text, and a voice draft (M3 capture and transcription, purpose `review`) that
    the customer edits and approves. Typing works without speech.
  - Repeat submissions return the stored review.
  - Tied to the booked services confirmed as completed.
  - Admin **Hide review** keeps the text, records a reason, and removes the review from the worker's view and
    from ratings.
- [x] **Dashboards:**
  - Bookings are grouped (awaiting confirmation, issues, booked and in progress, completed, cancelled or closed),
    with the next step for each role.
  - The worker sees **My work history**: completed jobs, average rating with count, and feedback per job, with
    no addresses or identities.
  - The worker's invitation inbox shows the booking status instead of "Open invitation".
- [x] **Recommendations:**
  - M6 filters are unchanged. Ranking is speciality relevance, then relevant confirmed jobs, then a smoothed
    visible rating, then review count, then UUID.
  - Cards show "N confirmed jobs including …", the rating with count or "No reviews yet" (never zero), and "New
    worker" until the first confirmed job.
  - Two grouped queries serve the whole list.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **337 passed**: 14 new for M9, including a **PostgreSQL race test** (confirm vs dispute ×3, each with exactly one winner; a duplicate review race → one review) |
| `check`, `makemigrations --check`, `migrate` | ✅ No issues; migrations `bookings.0002`, `voice.0004`, `reviews.0001` applied |
| Frontend typecheck / tests / build | ✅ No errors / **94 passed** (6 new) / built |

Backend tests cover:
- **Completion:**
  - request, a retry, and the worker cannot confirm;
  - the customer confirms and a retry adds no duplicate events;
  - both see `completed`, and the worker no longer sees the address;
  - a paused worker stays paused, the snapshot is unchanged, and the worker can then start another job.
- **Second starts:** blocked while awaiting confirmation (even 3 hours after the planned end) and while disputed.
  Overlapping acceptances are still refused; after a staff close the start works.
- **Terms:** an open change blocks the completion request; terms freeze afterwards.
- **Disputes:**
  - a note is required, and confirming after a dispute is refused;
  - staff without the permission are refused;
  - return to work, then close: no review, the invitation closes, and no work credit.
- **Admin views:** both need their permission (anonymous → login, staff without the permission → 403), and
  their effects and events are recorded.
- **Reviews:**
  - only after confirmed completion and only by the booking's customer (worker 403, stranger 404);
  - the rating must be 1–5; a repeat returns the original; a cancelled booking cannot be reviewed;
  - a voice review stores the proposal and the approved text, and the clip stays private;
  - worker feedback contains no private data;
  - hiding removes the review from the worker and from ratings.
- **Recommendations:**
  - confirmed work and a review lift a worker above an otherwise equal newcomer;
  - the card has history and a `completed_jobs` reason, and the newcomer has rating `null`;
  - hiding updates the count and rating but keeps the work count;
  - a 1★ worker ranks below an unrated worker with the same experience;
  - stats take two queries for five workers, and other services earn no credit.

**Flaky run:** one earlier full backend run reported `setUpClass` errors in two accounts test classes (admin and
CSRF). The same classes passed alone and in two later full runs (337/337); the cause was not identified.

The first full frontend run after the M9 changes had 7 tests time out, all unrelated to M9. A re-run passed
94/94, as did the final run after the last fixes.

### Urdu walk-through (three Chrome sessions at 360 px, real backend and PostgreSQL, fixture AI)

The rehearsal used a fresh fictional worker (03009990196), paused afterwards. The customer and worker both
used Urdu.

1. **Completion:** booking A was taken to In progress through the API. The worker tapped **گاہک سے تکمیل کی تصدیق
   مانگیں** and saw "waiting for the customer". The customer saw **کیا کام طے شدہ شرائط کے مطابق ہو گیا؟** and
   confirmed. Both then saw `completed`.
2. **Voice review:**
   - The recording became the editable draft "کاریگر وقت پر آئے، تینوں پنکھے صفائی سے لگائے…" (fixture
     transcript). The customer added "شکریہ۔" and gave 5 stars.
   - A second review attempt returned `200` with the stored 5★ review (`created: false`).
3. **Worker dashboard:** **میرا کام** showed 1 completed job, 5.0, 1 review and the review text. The feedback API
   contained no address.
4. **New request, same service:** the rehearsal worker ranked first with "کام مدد پر 1 تصدیق شدہ کام مکمل کیے جن
   میں شامل: چھت کے پنکھے کی تنصیب" and "5 میں سے 5.0 (1 ریویو)". The other five workers showed "نیا کاریگر" and
   "ابھی کوئی ریویو نہیں" (rating `null`).
5. **Dispute path:**
   - On booking B the customer chose **نہیں، کوئی مسئلہ ہے** with a reason and note, and the booking became
     disputed.
   - Starting booking C for the same worker → `409`.
   - Reviewing B → `409 review_not_allowed`.
   - The worker dashboard grouped the booking under "مسائل".
6. **Layouts:** no horizontal overflow on any of the 9 screens.

### Issues found and fixed

- The worker's invitation inbox still said "Open invitation" for booked or completed jobs, because the invitation
  stays active after booking; it now shows the booking status.
- Removed stale copy: the M4 "job requests come in a later version" line, and "reviews come later" in the M6
  card note.
- A warning icon on the "Completed" message was replaced (success state).

### Known limitations

- **Unanswered completion requests:** if the customer never responds, the booking stays awaiting confirmation
  and the worker cannot start another job until staff act. There is no automatic timeout, by design (no
  auto-completion).
- **Staff tooling:** dispute outcomes and hiding are minimal Admin form views. There is no queue, messaging or
  evidence handling; misconduct reports are M10.
- **Changes after the job:** none. Once completed, the terms and the review are final; reviews cannot be edited
  or replied to.
- **Reruns of the walk-through:** the rehearsal workers (03009990196–0199) remain in the development database,
  paused, and some are stuck in progress or disputed.

### Next module

**M10 Reporting and moderation:** reports linked to invitations and bookings (REP-01..03), staff decisions and
restrictions, reusing participant checks and `worker_eligibility`.

---

## M8 Quote acceptance, booking and arrival — complete (27 Nov 2026)

### Delivered

- [x] **M7 hand-off fixes** (migration `conversations.0002`):
  - Resolutions are now **"Existing quote terms confirmed"** or **"Terms changed"**. "Terms changed" keeps that
    version blocked (`revision_required`) until the worker sends a revised quote. Sources and resolution history
    stay with the version.
  - The agreement check is tracked as an **attempt**: it shows `running`, acceptance waits, and the provider is
    called outside transactions.
  - Results are saved only if the same attempt, version and unaccepted quote are still current under a row lock;
    late or stale results are discarded. A run that stalls becomes "could not run" (re-run or manual review).
  - An accepted quote and its approval record can no longer change.
- [x] **Acceptance** `POST /bookings/` (customer only):
  - Takes the invitation ID, the quote ID and version, and an idempotency key.
  - Locks job → invitation → quote → worker profile → worker account, then re-checks ownership, the active
    invitation, the exact current version, expiry, M7 readiness and `can_take_jobs` (pause ignored).
  - Rejects `[start, end)` overlaps.
  - Stores one booking with an immutable terms snapshot.
  - A retry with the same key returns the same booking. Stale, expired, blocked or conflicting acceptances get an
    actionable `409` with the current state.
- [x] **PostgreSQL guarantees** (migration `bookings.0001`, `btree_gist`):
  - one non-cancelled booking per job;
  - an exclusion constraint so a worker's open bookings never overlap;
  - one job in progress per worker;
  - one booking per acceptance key per customer.
- [x] **After booking:**
  - No new invitations or quote versions. Withdraw and decline send the user to the booking
    (`invitation_booked`).
  - Messages continue.
  - The exact address goes to the assigned worker on the booking only.
- [x] **Confirmed → Arrived → In progress:**
  - The worker reports arrival.
  - The customer issues a 6-digit code: `secrets`, stored only as an HMAC digest, 15 min, 5 wrong attempts
    (persisted), rate-limited, reissue invalidates, single use, shown only in the issue response.
  - The worker enters it. Starts are serialised per worker.
- [x] **Cancellation before start** (either person, with a reason): releases the slot, closes the invitation
  (`cancelled`) so its quote cannot be reused, invalidates codes and voids pending changes.
- [x] **Change proposals (QT-04):**
  - Old vs proposed terms; they apply only after the other person approves.
  - Time changes only before arrival, with the overlap re-checked under the worker lock.
  - The original agreement stays in `accepted_terms`.
- [x] **Status history** (`BookingEvent`) and the M9 hand-off: a booking in `in_progress` with its accepted terms,
  terms in effect, changes and history.
- [x] **Frontend:**
  - Accept review (exact terms, time, known charges, unknown parts, what happens next).
  - The booking detail screen for both roles (status steps, address, terms and original, arrival code, changes,
    cancellation, history).
  - "My bookings" on both dashboards, and booking links from the request, invitation and conversation screens.
  - After an uncertain network result, the screen reloads booking state before offering acceptance again.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **323 passed**: 26 new for M8, including **4 PostgreSQL concurrency tests** (two customers accepting overlapping slots ×3 → one booking each time; a double tap with one key → one booking; accept vs withdrawal ×3; accept vs revision ×3) |
| `check`, `makemigrations --check`, `migrate` | ✅ No issues; migrations applied (including `btree_gist`) |
| Frontend typecheck / tests / build | ✅ No errors / **88 passed** (8 new) / built |

Backend tests cover:
- **Acceptance:**
  - exact terms, and a retry returning the same booking;
  - other keys → `job_already_booked`; reused key → `idempotency_key_reused`;
  - stale, expired and blocked quotes;
  - a paused worker can be booked; an ineligible worker cannot;
  - overlap refused, adjacent slots allowed.
- **Frozen after booking:** quotes, withdraw, decline and new invitations are refused, while messages still work.
- **Privacy:** the address goes only to the booked worker and is gone after cancellation; other accounts get 404
  on every booking endpoint; accepted terms cannot be overwritten.
- **M7 fixes:**
  - "terms changed" blocks until a revised version, and v2 can then be accepted;
  - "terms confirmed" resolves;
  - a running check blocks, and a stalled one allows manual review;
  - a late result from an old attempt, or after acceptance, is discarded.
- **Arrival codes:**
  - only after arrival, customer-only, and never in any response or log;
  - wrong attempts persist and lock the code at 5; reissue invalidates the old code;
  - expired and missing codes; a single successful start;
  - a second job cannot start while one is in progress.
- **Cancellation:** releases the slot, closes the invitation, the old quote cannot be reused, and the customer can
  invite again; it is refused after the start.
- **Changes:**
  - both approvals are needed, and the original is kept;
  - time changes re-check overlaps when proposed and when approved;
  - no time change after arrival; "no change" is rejected;
  - a scope change during the job works, and the proposer can withdraw.

### Two-session walk-through (three Chrome sessions at 360 px, real backend and PostgreSQL)

All AI providers were **fixtures** in this run; no live AI calls were made during M8. A **fresh fictional
rehearsal worker** was used for each run (03009990197; earlier runs 0198 and 0199). Each is paused afterwards, so
the demo workers 0101–0104 are untouched.

1. **Acceptance:** the customer (Urdu) opened the conversation and tapped **Review and accept**. The review showed
   the time, known charges, "nothing unknown" and that the address will be shared. **Accept and book** opened the
   booking.
2. **Worker** (English, second browser):
   - **My bookings** showed the booking, which included the exact address. The conversation API still had no
     address.
   - Decline and a new quote on the booked job returned `409`.
   - **I have arrived**.
3. **Code:**
   - The customer saw the arrival by polling and revealed a 6-digit code. The worker's booking response did not
     contain it.
   - A third account got `404` on the booking, code and start.
4. **Start:** the worker entered a wrong code ("Attempts left: 4"), then the right one, and the booking moved to
   **In progress**. The code was then used and inactive.
5. **Change during the job:** the worker proposed a third fan. The customer saw "now 2 / proposed 3" and the totals
   (PKR 1,200 → 1,800), then approved. The terms in effect became 3 / 1,800, and the original stayed 2 / 1,200.
6. **Cancellation:**
   - A second booking was cancelled by the worker with a reason. Accepting the old quote again →
     `409 invitation_not_active`, and the invitation now shows `cancelled`.
   - Another customer then booked the same slot → `201`.
7. **Overlap and one job at a time:** an overlapping acceptance → `409 schedule_conflict`. Starting another job
   while one was in progress → `409 worker_has_job_in_progress`.
8. **Layouts:** no horizontal overflow on any of the 10 screens.

### Issues found and fixed

- The quote panel treated a missing `booking_id` (older payloads) as "booked"; it now checks for a real ID.
- The worker's code was sent with the spaces people type ("482 913"); it is now sent as digits (the server also
  strips spaces).
- The wrong-code count now uses M2's detail name `attempts_remaining`, so the existing Urdu/English message
  shows the number.
- **Urdu bidi:**
  - amounts in the acceptance breakdown are isolated as LTR;
  - generated lines in the change comparison ("فی عدد PKR 600 × 2 …") follow the UI direction instead of the
    dominant script.

### Known limitations

- **Arrival:** "I have arrived" is self-reported, with no time window or GPS. The customer's code is what
  confirms it, for this booking only.
- **Code display:** the code is shown once. After leaving the screen the customer issues a new one, and the old
  one stops working.
- **Updates:** booking screens refresh by polling (10 s). There are no push notifications.
- **Booking time:** the time is the accepted quote's start/end. There is no separate "60-minute suggestion"
  window editor; both people agree the time through the quote (and later through a change).
- **Changes:** a proposal carries the full set of terms; only one change can be pending at a time.
- **Workers stuck "in progress":** a worker with a job in progress cannot start another job until M9 adds
  completion. This applies to the three rehearsal workers in the development database, and to any demo worker
  whose booking you take to "In progress".
- **Staff tools:** bookings are read-only in Django Admin (staff actions come with M9/M10).

### Environment needed

The same as M7; run `python manage.py migrate`. The database user must be able to create the `btree_gist`
extension, which is true for the Docker database. The optional settings are `ARRIVAL_CODE_TTL_MINUTES`,
`ARRIVAL_CODE_MAX_ATTEMPTS` and `AGREEMENT_CHECK_STALE_SECONDS`.

### Next module

**M9 Completion and feedback:** completion requested → confirmed or disputed, from an `in_progress` booking.
- Extend the reserving statuses and constraints.
- Use the same lock order.
- Reviews only after confirmed completion.

---

## M7 Private conversation, quotations and agreement gaps — complete (27 Nov 2026)

### Delivered

- [x] **Conversation per invitation** (`apps/conversations`, migration `conversations.0001`; voice `0003` adds the
  `message` audio purpose):
  - Only the job owner and the invited worker can read, play or write; everyone else gets `404`.
  - Writes need an active invitation (`409 conversation_closed`). History stays readable after a decline or
    withdrawal.
  - Text messages and **voice notes**. The sender reviews or edits the proposed Urdu caption before sending.
    The original audio, the automatic proposal and the approved caption are stored separately, and both sides
    see "Caption unavailable" when there is no caption.
  - Playback is private and `no-store`. Draft uploads stay owner-only.
  - Messages are immutable. A device-generated `client_id` makes retries return the stored message.
  - Paginated (30) with `after`/`before` cursors. The client polls every 5 s without touching text being typed.
- [x] **Structured, versioned quotes:**
  - Terms: scope, quantity, labour (whole job or per item), materials responsibility and amount,
    visit/inspection fee and treatment, exclusions, start/end.
  - Money is Decimal PKR; totals are computed on the server; unknown amounts stay unknown (never zero).
  - Inspection-only quotes are supported.
  - Submitted versions are frozen (database constraint). A revision supersedes the previous version, and
    history is kept.
  - A version expires at min(24 h, start time).
  - Submit and invitation closure are concurrency-safe: lock order job → invitation → draft, with the
    invitation re-checked inside the transaction.
- [x] **Agreement-gap check:**
  - Deterministic rules (time outside the requested window; materials cost unknown).
  - The configured checker (`AGREEMENT_CHECK_PROVIDER`: Gemini, or a labelled demo fixture) gets the shared
    request summary, approved message texts and the quote terms only. Every finding must quote source
    statements that appear in that input; others are dropped.
  - Findings show the statements word for word, a short question and who should answer. They are tied to
    the quote version and are resolved explicitly (clarified / not a conflict) with a required note; a changed
    price means a new, re-checked version.
  - A checker that cannot run shows "could not run" (never a pass). The check can be retried, or the customer
    can record a manual review.
- [x] **M8 hand-off:** `GET /conversations/{id}/readiness/` →
  `{invitation_id, quote_id, version, expires_at, ready, blocking[], warnings[]}`. The UI shows **"Ready for
  customer acceptance"** or the blocking reasons. Acceptance, booking, reservation and arrival codes are not
  built.
- [x] **Frontend:**
  - `/conversations/:id`, with links from the customer's open invitation and invitation history and from the
    worker's invitation page.
  - The same structured quote card for both sides, with Urdu/English read-aloud of the key terms.
  - The worker's quote form uses icon tiles and Pakistan time.
- [x] `check_ai_providers --only agreement_check` runs the configured checker on a fictional labour-vs-materials
  sample.

### Checks (27 Nov 2026)

| Check | Result |
|---|---|
| Backend tests (real PostgreSQL) | ✅ **297 passed**: 20 new for M7, including **2 PostgreSQL concurrency tests** (threads, separate connections): 5 submit-vs-withdraw races never leave a version submitted after closure; a double submit gives one version |
| `check`, `makemigrations --check` | ✅ No issues, no pending migrations |
| Frontend typecheck / tests / build | ✅ No errors / **80 passed** (9 new) / built |

Backend tests cover:
- Two accounts exchange text and a voice note, and a third customer and another worker get `404` on the
  header, messages, audio and send.
- A draft clip stays private.
- Captions: approved, typed and unavailable.
- Retrying a send stores one message.
- Pagination and polling.
- After a decline or withdrawal, history stays readable while sends, drafts, submits and resolutions are blocked.
- The labour-vs-materials conflict:
  - it is reported with sources, and a clarification plus revised v2 reaches ready;
  - v1 keeps its terms and findings, and its readiness says superseded.
- An explicit not-a-conflict resolution needs a note.
- Every validation code, plus totals with an unknown amount.
- Inspection-only quotes.
- Expiry at min(24 h, start).
- The timing rule.
- Checker failures:
  - unexpected errors and an unconfigured provider become "unavailable", never a pass;
  - the customer-only manual review;
  - re-running the check.
- Roles: drafts are the worker's only.
- No private fields reach the checker, and times reach it in one Karachi format.
- Invented sources are dropped, and the Gemini request has the right shape (mocked).

### Two-account walk-through (three Chrome sessions at 360 px, real backend and PostgreSQL)

All AI providers used **fixtures** here; the screens labelled the check "Simulated result (not real AI)".

1. **Customer (Urdu)** confirmed a request saying *"1200 روپے سامان سمیت"*, invited demo worker 03009990101,
   opened the conversation from **Find a worker** and sent a text.
2. **Worker (English, second browser)** opened it from the invitation page.
   - The page showed no address or access notes.
   - The worker uploaded a voice note, reviewed the proposed Urdu caption and sent it.
   - The customer received it by polling. Text the customer was typing was kept.
   - The audio played (`200 audio/wav`, `private, no-store`), and the automatic proposal was not exposed to the
     customer.
3. **Third account:** a new customer got `404` on the header, messages, audio, quotes and send. Demo worker
   03009990102 got `404` on the header and audio.
4. **Retry:** the same `client_id` sent twice gave `201` then `200`, with the same ID and one stored message.
5. **Quote v1** (600 per item × 2, customer supplies materials):
   - The check flagged `materials_responsibility`, quoting the request sentence and the quote's materials
     term.
   - Both sides saw "Not ready", the readiness API said `unresolved_findings`, and the card showed
     PKR 1,200 known total.
6. **Clarification and v2:**
   - Customer and worker clarified in the chat. The worker sent v2: whole job PKR 1,500, materials included.
   - v1 became `superseded` and kept its terms and finding.
   - The fixture flagged v2 too, because the worker's earlier voice note said the customer would buy the
     materials. The customer resolved it with a note.
   - Both saw **Ready for customer acceptance**. Readiness: `ready: true`, version 2, `expires_at` 24 h after
     sending.
7. **Withdrawal:** the customer withdrew. The conversation stayed readable from the invitation history.
   - Sends and draft saves returned `409`; the 5 messages were kept; readiness said `invitation_not_active`.
   - Both screens showed the closed notice and no composer.
8. **Layouts:** no horizontal overflow on any of the 13 screens.

### Which AI checks ran live

| Capability | How it was checked | Result |
|---|---|---|
| Agreement check, fixture | Tests, walk-through, `check_ai_providers` | ✅ Labelled simulated. Keyword rules for the materials example only |
| Agreement check, **live Gemini `gemini-3-flash-preview`** | `check_ai_providers --only agreement_check` on the fictional sample | ✅ One correct `materials_responsibility` finding, quoting the request, the worker's message and the quote term exactly (11.9 s) |
| Agreement check, live Gemini `gemini-3.6-flash` (the configured default) | Same | ❌ Provider timeouts, then `503`, on two attempts. Reported as `ai_provider_unavailable`, which the app shows as "could not run" |
| Voice-note caption (speech-to-text) | Walk-through with the fixture transcript | Fixture only in M7. The live Gemini transcription path is the same as M5's |
| Quote read-aloud | Walk-through with fixture TTS | Fixture only in M7. ElevenLabs was live-checked in M3 |

### Issues found and fixed

- **Live Gemini output was truncated** (`status: incomplete`, invalid JSON): thinking used about 1,050 of the
  1,500-token budget. The budget is now `GEMINI_AGREEMENT_MAX_TOKENS` (default 6000).
- **Live false positive on time:** the request window was sent in UTC and the quote in +05:00, and the model
  reported the same instant as a conflict. Both are now sent in one Asia/Karachi format, and the instruction
  says equal times and unknown amounts are not conflicts. A test was added.
- `readiness.expires_at` used a different timestamp format from the rest of the API. It is now UTC `…Z`
  everywhere.
- The conversation composer passed an unstable callback to `VoiceCapture`. After a real microphone recording,
  that would have reset the caption on every render; the callback is now stable.
- Read-aloud said "1,200. روپے" (the regex took the full stop) and used "." in Urdu. Fixed and unit-tested.
- **A test run used development settings:** I once ran `manage.py test` without `--settings`. It loaded the real
  Gemini key from `.env`, and one transcription test made a live call; the audio was a generated test tone and
  the call timed out. `manage.py test` now defaults to `config.settings.test`.
- Quantity 0 or 1000 gave the generic "must be zero or more"; it now gives `quantity_out_of_range`. The fixture's
  question now follows the language of the statement it quotes (Urdu for Urdu).

### Known limitations

- **Demo fixture:** the agreement fixture only recognises the materials example. Other contradictions in demo
  mode need the live checker.
- **Live model:** the live checker was verified with `gemini-3-flash-preview` only. The default
  `gemini-3.6-flash` was overloaded during testing. Model output is advisory: it can miss contradictions or
  raise false ones, which is why every finding shows its source statements and needs an explicit, noted
  resolution.
- **Resolving points:** either participant can resolve a point. There is no separate confirmation by the other
  person; customer acceptance of a specific version is M8.
- **Updates:** messages and quotes update by polling (5 s / 15 s). There are no push notifications.
- **Translation:** messages are not translated between Urdu and English.
- **Privacy in messages:** messages carry a privacy hint, but are not scanned automatically for phone numbers or
  addresses (unlike the M6 shared description).

### Environment needed

The same as M6. For a live agreement check, set `AGREEMENT_CHECK_PROVIDER=gemini` with `GEMINI_API_KEY`, and
optionally `GEMINI_AGREEMENT_MODEL` / `GEMINI_AGREEMENT_MAX_TOKENS`. Run `python manage.py migrate` after
pulling.

### Next module

**M8 Booking and arrival.** Customer acceptance of the ready `quote_id`/`version`:
- re-check `readiness()` inside the same lock order (job → invitation → quote);
- booking and time reservation;
- arrival codes.

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
