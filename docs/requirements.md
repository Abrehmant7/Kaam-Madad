# Kaam Madad — Requirements Reference

> **Name note:** the product's public name is now **Kaam Madad (کام مدد)**. The source PDF below describes
> the same project under its previous name, *Roshan Rozgaar*. Every requirement, requirement ID and module
> ID (M1–M11) applies unchanged; read "Roshan Rozgaar" in the PDF as "Kaam Madad". References below to
> "the earlier Roshan Rozgaar repository" mean the old prototype, which must still not be reused.
>
> Source: *Roshan Rozgaar — Software Requirements and Codex Implementation Brief*, **v1.0, 24 November 2026**
> (Capital Youth Expo, Track 5 — Urdu & Regional Tech).
>
> This file is a faithful, readable restatement of that PDF so later modules keep the full context.
> Requirement IDs are preserved exactly. Where wording is condensed, meaning is unchanged. If this file
> and the PDF ever disagree, **the PDF wins** — fix this file.
>
> Requirements describe a **target**, not functionality that already exists. See
> [progress.md](progress.md) for what is actually implemented.

---

## 0. Product, scope, and ground rules

**Product.** A mobile-first marketplace connecting customers with nearby skilled tradespeople. A worker
must be able to complete the core journey **without understanding English**. Urdu text, spoken
instructions, recognisable icons, and guided choices support that journey.

**Authority.** The current team-approved conversation and the v1.0 specification replace the earlier
project-description draft where they differ.

**Implementation approach.** Build new project-specific code from scratch. **Do not import or adapt the
earlier Roshan Rozgaar repository.** Generic frameworks and libraries are allowed and must be disclosed.
Maintain genuine development history and document the earlier prototype as inspiration only.

### Core product decisions

- Preserve the worker–customer marketplace. Agreements are one part of the booking flow.
- Worker onboarding: short voice introduction → CNIC capture and verification status → three guided
  speciality questions → service-area confirmation.
- Speciality questions are read aloud and answered with **labelled icon choices**. They are **not** an
  open-ended voice interview or an automated skills examination.
- Customers use a simple Urdu/English signup, with optional voice assistance for **non-secret** profile
  information. They describe a job, choose a recommended worker, and negotiate with that worker.
- AI supports speech interpretation, CNIC field extraction, semantic service matching, and
  agreement-gap detection. **Users approve consequential information; server code controls actions.**
- Initial trades: **electrician, plumber, AC technician**. Catalog entries and service areas are
  **database content**, not hard-coded screen logic.
- Initial pilot: Islamabad/Rawalpindi sample areas. Architecture must not restrict future coverage to a
  few sectors.
- Currency is **PKR**. **No** in-app payments, escrow, automatic pricing, government background checks,
  or autonomous AI bookings.

### Build priorities

| Priority | Scope |
|---|---|
| **Required** | Both role journeys, Urdu/English UI, real speech adapter, speciality choices, location fallback, identity status, requests and optional images, recommendations, private messages, versioned quotations, gap resolution, consistent bookings, arrival code, completion, reviews, reports, admin handling. |
| **Conditional** | Real NADRA verification only if authorised access is obtained. Otherwise a clearly labelled demonstration/manual-review route. **A failed or missing provider must never silently produce a verified result.** |
| **Deferred** | Native apps, live GPS tracking, open-ended voice control of every screen, complex calendar optimisation, multi-worker crews, learned ranking from demo data, automated skill certification, full accounting system. |

---

## 1. Roles, access, and end-to-end journeys

### Roles

- **Worker** — owns their profile and verification submission; receives targeted requests; messages,
  quotes, accepts work through the confirmed-quotation flow, enters an arrival code, requests completion,
  reports misconduct.
- **Customer** — owns job requests; receives recommendations; chooses a worker; exchanges messages;
  accepts quotations; views the arrival code; confirms completion; rates/reviews; reports misconduct.
- **Staff** — reviews permitted identity evidence and reports through **Django Admin**. Staff decisions
  record actor, time, reason, and the exact checks performed. **Staff never obtain access simply by
  changing a client-side role.**

**AUTH-01** — One account has one marketplace role in the MVP; role switching is out of scope. Staff
access uses separate server-authorised permissions. Customers and workers can edit only their own
records and access only conversations/bookings in which they participate.

### Worker journey

1. Select language and worker role. Hear introductory instructions. Create credentials through the
   accessible account flow.
2. Record a short introduction; review/correct extracted non-secret profile fields.
3. Capture CNIC, review extracted identity fields, consent to the selected verification method, and see
   the truthful verification/review state.
4. Answer three trade-specific questions using icon tiles: services offered, primary specialities,
   services not offered. Instructions and labels can be played aloud.
5. Confirm browser-derived location or choose an area manually; select where they will travel for work.
6. Confirm the profile and choose whether to receive requests. Booking eligibility follows §3 rules.
7. Open targeted requests, listen to job information and voice notes, view optional images, negotiate,
   and submit a structured quotation.
8. Receive booking confirmation after customer acceptance succeeds on the server. On arrival, enter the
   customer's code, perform the work, and request completion.
9. View completed-job feedback and report customer misconduct during or after the interaction.

### Customer journey

1. Sign up/login using a simple Urdu/English form. Optional voice assistance can draft name and area,
   **never passwords or authentication codes**.
2. Describe the job by recording or typing. Confirm the interpreted description, category, location,
   preferred date/time, and optional images.
3. Review suitable workers and the reasons for recommendations; select one to send the confirmed details
   privately.
4. Exchange voice/text messages, clarify the job, review quotations and agreement gaps, and accept the
   current quotation.
5. View the assigned worker's profile and booking. When the worker arrives, check the person against the
   profile and share the booking-specific arrival code.
6. Confirm completion or raise an issue; give one rating/review for an eligible completed booking.
   Report misconduct during or after the interaction.

---

## 2. Architecture, accounts, and language foundation

### Implementation baseline

| Layer | Decision |
|---|---|
| Backend | Django with Django REST Framework; one application deployment |
| Database | PostgreSQL; Django migrations and transactional booking services |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Authentication | Django sessions with HttpOnly cookies and CSRF protection; same-origin production deployment |
| Moderation | Django Admin with explicit staff actions and audit records |
| AI/audio | Backend provider adapters for speech-to-text, interpretation, OCR, and speech synthesis |
| Media | Private storage behind authorised downloads; local private storage in development, replaceable in production |
| Updates | Polling for request, conversation, and booking changes; WebSockets deferred |
| Local development | PostgreSQL through Docker Compose or an existing instance; clear Windows and Linux instructions |

These are chosen defaults, not a mandate for a cloud vendor. Select maintained dependency versions at
implementation time and record resolved versions in lock/dependency files. **Do not add microservices,
Redis, Celery, a vector database, or an agent framework** unless a demonstrated requirement needs them.

**AUTH-02** — Internal opaque user ID. Phone number + password are the default login credentials;
**CNIC must not be a public username**. Normalise Pakistani phone numbers consistently and enforce
uniqueness. Mask private identifiers in responses and screens.

**AUTH-03** — Phone ownership verification is an adapter-backed capability. A production pilot requires
a real OTP provider. Demo OTP flows must be visibly simulated, server-controlled, rate-limited, and
unavailable in production mode. Phone confirmation does not establish legal identity.

**AUTH-04** — Hash passwords with Django's supported facilities; never send passwords or OTPs to AI.
Provide signup, login, logout, current-user, and CSRF bootstrap endpoints. Public signup must not create
staff users.

**UX-01** — Urdu is the initial language; English via a persistent switch. Use translation keys, not
scattered literal strings. Urdu uses real Urdu script, RTL layout, a locally bundled readable font, and
correct mixed-direction rendering for phone numbers, amounts, dates, and codes.

**UX-02** — Large labelled controls, accessible focus, clear loading/error states, replayable
instructions, icon **plus** text for every critical action. 44 CSS-pixel minimum touch targets. Neither
colour nor an icon alone conveys a decision. Test at 360-pixel mobile width.

**UX-03** — Fixed onboarding instructions may use prerecorded Urdu/English audio. Dynamic job/quote
read-aloud uses a tested speech provider. If a voice is unavailable, show a retry and readable fallback;
do not silently promise speech the device cannot produce.

---

## 3. Worker onboarding and identity status

**WK-01 Voice introduction** — Record, replay, retry, and submit a short introduction. Extract only
supplied fields (e.g. name, broad trade). Keep a draft until confirmed. Never invent experience,
certificates, working areas, or skills. Credentials remain separate from speech input.

**ID-01 CNIC extraction** — Capture/upload a CNIC image into private storage. OCR extracts available
name, CNIC number, expiry date. Validate format, request confirmation, permit correction or recapture.
Missing expiry or unreadable fields trigger review; OCR format checks do not authenticate a document.

**ID-02 Provider verification** — The identity adapter accepts confirmed details and consent, then
records a provider reference and outcome. Real NADRA verification requires authorised access and an
implemented provider contract. **A CNIC upload, OCR success, face photograph, or manual staff decision
must never be labelled NADRA verification.**

**ID-03 Account-holder check** — A real-pilot identity process must also bind the applicant to the
identity, through an approved verification method or documented in-person review. An uploaded selfie
alone is not a reliable liveness/identity check. **Do not build an improvised AI face-matching service.**

### Verification states

| State | Meaning and booking policy |
|---|---|
| Draft / pending | Submission incomplete or awaiting review; no bookable public profile |
| Needs correction | Worker receives a specific, accessible correction request |
| Provider verified | Real authorised provider returned success; show exact method |
| Manually reviewed | Staff completed documented checks; display method and limitations |
| Demo approved | Fictional/test record approved for a demo only; persistent demo label |
| Rejected / expired / suspended | Cannot accept new bookings; preserve existing records for review |

**ID-04** — Production eligibility requires a valid accepted verification method and an active account.
Demo-approved workers are bookable **only in an explicitly separate demo deployment**. No mixed
production/demo directory. Existing booking incidents after suspension require staff handling rather
than automatic silent cancellation.

**WK-02 Specialities** — After trade selection, read three short questions aloud and show labelled
multi-select icon tiles: (1) services offered, (2) primary specialities (subset of offered),
(3) services not offered. **Offered and excluded sets cannot overlap.** Conflicting choices are explained
and the worker is asked to correct them.

**WK-03** — Specialities are worker declarations, not assessed qualifications. Experience is
self-reported. Identity status and skill claims appear separately. A future certificate/assessment record
must identify issuer/assessor, scope, date, and method.

**WK-04 Location** — Ask browser permission after explaining the purpose. Show the detected area for
confirmation. Handle denial, timeout, unsupported browser, and inaccurate coordinates with manual
selection. Record service areas/travel radius separately from current location. **Never expose exact
worker coordinates publicly.**

**WK-05 Profile** — Read a short summary; allow correction; save/publish only after confirmation and
eligibility checks. Store the accepting-requests preference separately from reservation state. **A
completed job must not turn a paused worker back on.**

---

### M4 amendments (27 Nov 2026)

The project owner's M4 brief (27 Nov 2026) changes the following requirements. Where it conflicts with the
PDF text above, this amendment wins for M4 and later modules.

- **Worker journey order** (replaces steps 1–5 of §1 "Worker journey"):
  1. Create the account: mobile number, password and confirmation. The worker role is preselected from
     "مجھے کام چاہیے", and the fixed password instruction can be played aloud.
  2. Choose the work: trade, services offered and **one** main speciality (from the selected services). Services
     not offered are optional, under "More options".
  3. Choose the city and the service areas the worker is willing to travel to.
  4. Then the dashboard. Phone confirmation moves there.
  - Progress is saved per screen, and the server decides completion.
- **WK-01 voice introduction** becomes an optional profile enhancement after onboarding.
- **WK-02:** one main speciality instead of 1–3; the offered/excluded rules are unchanged.
- **WK-04 location:** no browser geolocation or GPS. Manual selection of active catalog areas inside one city.
  These are travel areas, not the worker's location.
- **Identity (ID-01, ID-02, ID-04):**
  - **OCR:** real OCR with **Tesseract on the backend host** reads the printed English **name** and the
    **CNIC number** from a photo of the card front. The worker reviews and corrects both fields; corrections
    are kept distinct from the scan. There is no simulated OCR.
  - **Images:** photos are validated (type, size, dimensions) and not retained.
  - **Registry:** only the registry is simulated. Name **and** number must match the same fictional record,
    and success reads "Demo identity check passed. Name and CNIC number matched our demo registry." A fictional
    address may be shown labelled "Demo address".
  - **Approval:** demo approvals count only in demo mode; NADRA stays unconfigured.
  - **Before approval:** verification is started from the dashboard, and the dashboard and profile editing
    work before approval.
- **Customer signup:** one screen (customer preselected from "مجھے کاریگر چاہیے"), then the customer dashboard
  with phone confirmation. The job's service area is asked when the job is created (M5). There is no customer
  CNIC and no required display name.

---

## 4. Customer requests and worker selection

**JOB-01 Draft request** — Customer records or types a job in Urdu/English. AI drafts a faithful Urdu
description and service tags. Preserve the original input. Ask targeted clarification when required
details are missing/uncertain. Do not infer a technical diagnosis from symptoms or images.

**JOB-02 Required fields** — Confirm description, category/task tags, area, private address when
supplied, preferred date/time window, access conditions. Optional: images and a budget explicitly
described as the customer's preference. The preferred window may be refined during negotiation; **the
accepted quote fixes the booking window.**

**JOB-03 Date/time** — Present in **Asia/Karachi**; store timezone-aware timestamps in **UTC**. Clarify
ambiguous phrases such as "kal shaam". Reject past booking windows. Read back resolved date, time, and
location before submission.

**JOB-04 Media** — Optional JPEG/PNG/WebP images and supported audio formats within documented limits.
Server validates size, content type, and file content; client checks are supplementary. Remove image
location metadata where feasible. Automated visual fault diagnosis is out of scope.

**REC-01 Eligibility** — Recommend only complete, eligible, active workers accepting requests, serving
the location, offering relevant services without an explicit exclusion. If a time is known, consider
overlapping reserved windows. Recheck eligibility when inviting and booking; **a recommendation is not a
reservation.**

**REC-02 Ranking** — AI interprets everyday job language into catalog tags. Rank eligible workers by a
documented combination/order of task relevance, service-area fit/approximate distance, relevant
completed-job history, and contextual review information. Start with understandable rules + semantic
matching, **not a learned model trained on demo data**.

**REC-03 Transparency** — Explain recommendations using stored facts; distinguish claimed skills from
completed work; show review counts; identify new workers. No invented credentials, guaranteed arrival
times, or unjustified numerical confidence. Straight-line/area-centre distance is labelled approximate.

**JOB-05 Targeted invitation** — Customer chooses one recommended worker; confirmed job details become an
invitation and private conversation. Workers see only requests specifically sent to them. An invitation
does not reserve either party.

**JOB-06 MVP negotiation rule** — **One active worker invitation per request.** Worker can decline;
customer can withdraw before booking and choose another worker. Closing an invitation invalidates its
quotations and closes sending in that conversation, while preserving authorised history. Re-inviting
creates a new invitation identity. Parallel bidding is deferred.

---

## 5. Voice, descriptions, private communication, and media

**AI-01 Provider boundaries** — Separate interfaces for speech-to-text, text interpretation, OCR,
text-to-speech, and identity verification, even if one vendor implements several. Keys live on the
server. Mock implementations are deterministic, labelled, and isolated from production.

**AI-02 Structured interpretation** — Validate model output against explicit schemas. Distinguish
supplied, missing, and uncertain fields. Treat transcripts and uploads as untrusted content, not
instructions. **AI cannot directly publish profiles, submit quotes, accept bookings, or change identity
status.**

**AI-03 Reliability** — Push-to-talk clips **≤ 60 s, ≤ 10 MB**; images **≤ 5 MB each, ≤ 5 per
request**. Configure limits centrally. Timeouts, bounded retries, understandable failure messages,
preserved drafts. Test browser recording codecs on the demo phones.

**AI-04 Confirmation** — Preview the interpretation with replay/correct controls before sending.
Monetary values, material treatment, date/time, exclusions, and service location require explicit
confirmation. If interpretation fails, keep the original voice note and allow manual Urdu entry/guided
choices. **Failure must not silently fabricate a successful interpretation.**

**MSG-01 Conversation** — Private text and voice notes within an invitation/booking. Normal path: original
audio + sender-approved Urdu description. English translation/read-aloud on demand. A fallback message
without a description must explicitly show that interpretation is unavailable.

**MSG-02 Read-aloud** — Structured playback of job category, description, area, requested date/time, and
quotation conditions in the selected language. Protect exact address and private attachments. Fixed
instruction audio can be cached; **dynamic private audio must not enter a shared public cache.**

**MSG-03 Message integrity** — Record sender, invitation/booking, timestamps, source audio, interpreted
text, confirmed text. Sent messages are immutable; corrections are new messages. Client request IDs
prevent duplicate sends after retries. Polling fetches new items without erasing a local draft.

**MEDIA-01 Access** — Media URLs are authorised or short-lived and tied to the correct participants. CNIC
files are never message attachments or public profile assets. Random filenames alone are not access
control. Enforce private media checks on every download; avoid private identifiers in filenames/logs.

**Acceptance examples** — Preserve "rewinding nahi karta"; distinguish 1,200 from 1,500; distinguish
total from per-item price; confirm "kal"; denied microphone falls back to text or file upload; screen
stays usable if TTS fails.

---

## 6. Quotations and agreement-gap detection

**QT-01 Structured quote** — Scope, quantities where relevant, labour amount, total-vs-unit basis,
materials included/excluded/customer-supplied, any agreed materials amount, visit/inspection fee and its
treatment, exclusions, proposed start/end window. **All amounts are PKR decimals, never floating-point.**

**QT-02 Inspection** — A visit-only quotation explicitly identifies the inspection fee and any waiver
policy. **Unknown repair/material costs remain unknown, not zero.** Inspection-only work does not imply
acceptance of a later repair quotation.

**QT-03 Versioning** — Worker confirms and submits an **immutable** quote version. Revisions create a new
version and supersede previous acceptance eligibility. Customer can accept only the latest valid,
unexpired quotation of the current invitation. Quotes expire after **24 h or the proposed start time,
whichever comes first** (configurable).

**GAP-01 Detection** — Compare confirmed request details, approved message descriptions, and quote fields
for missing/contradictory scope, item counts, unit/total price, material responsibility, visit fees, and
timing. Show source statements. Deterministic validation for required fields and arithmetic; AI flags
possible semantic ambiguity.

**GAP-02 Resolution** — A conflict is a clarification prompt, not a fraud accusation or automatic answer.
Ask the appropriate party. Worker revises the structured quote where needed; customer accepts the same
final terms. Record resolution, actor, quote version. **Unresolved required fields and identified
material conflicts block acceptance.** A false positive is resolved with explicit corrected terms, not
silently discarded.

**GAP-03 Limits** — No flag ≠ agreement or legal validity. Always present the final structured summary
and an explicit acceptance action. The app does not determine market prices, legal enforceability, or
who is truthful.

**QT-04 Changes after booking** — Extra task or changed price → change proposal with old/new scope,
amounts, timing. Existing agreement stays effective until both approve. Recheck scheduling before
accepting a time change. Preserve the original accepted version and each accepted change.

**Example** — Customer expects two fans installed for Rs. 1,200 including materials; worker states
Rs. 1,200 labour with customer-supplied materials → flag material responsibility, clarify, corrected
quotation, customer acceptance. A third fan later requires a separately accepted change.

---

## 7. Booking, availability, arrival code, and completion

### Booking state model

| State | Actor/action and effect |
|---|---|
| Confirmed | Customer accepts current quotation; server creates reservation atomically |
| Arrived | Assigned worker reports arrival; reservation remains active |
| In progress | Worker successfully submits the customer-visible arrival code |
| Completion requested | Worker reports done; reservation remains active pending response |
| Completed | Customer confirms; reservation releases and feedback becomes eligible |
| Cancelled | Allowed cancellation action records actor/reason and releases reservation |
| Disputed | Customer raises a completion issue; staff resolves reservation/outcome explicitly |

**BK-01 Atomic acceptance** — Validate customer ownership, current invitation, quote version/expiry,
resolved gaps, account eligibility, scheduling. In one DB transaction: **lock the job request, then the
worker**, recheck, store the exact accepted quote, create one booking. Enforce one non-cancelled booking
per request. All acceptance paths use the same service and lock order.

**BK-02 Scheduling** — Agreed start/end windows with an editable 60-minute initial suggestion; both users
confirm the final window. No overlapping nonterminal reservations per worker using half-open intervals
**[start, end)**. Lock the worker while checking and creating/updating a reservation. A job still in
progress/completion review after its planned end also blocks another job from starting. No route
planning or automated rescheduling.

**BK-03 Idempotency** — Repeated acceptance with the same customer/request key returns the original
booking. A stale quotation, competing request, or conflicting reservation returns an actionable **409**
with current server state. After a network timeout, retrieve state before inviting a repeat acceptance.

**BK-04 Arrival code** — After the worker marks arrived, the customer can reveal a server-generated
**6-digit** code for that booking. Store only a secure digest. Expires after **15 min**, at most **5
failed attempts**, rate-limited issuance and validation. Reissue invalidates the old code. **The worker
never receives the code through an API response**; only the owning customer can view it.

**BK-05 Identity boundary** — Customer checks the worker's profile/photo before sharing the code. Code
validation establishes the booking interaction, not government identity, GPS presence, competence, or
safety — say so in concise product copy. No automatic face-recognition claim.

**BK-06 Completion/cancellation** — Worker requests completion; customer confirms or reports an issue. No
automatic five-star rating or completion when the customer is absent. Before start, either party may
cancel with a reason. After start, use the issue/dispute route for staff review. Define and audit staff
resolution actions.

---

## 8. Feedback, recommendation improvement, and misconduct reports

**REV-01** — Customer submits one 1–5 rating and review per owned completed booking. Voice review → draft
Urdu comment, confirmed before submission. Tie feedback to actual agreed/completed task tags. A review
cannot confer an identity or qualification badge.

**REV-02** — Worker dashboard: completed jobs, current engagements, rating with review count, job-specific
feedback. Sample histories/reviews explicitly marked in the demo. Staff can hide an abusive review with
an audit reason; no silent rewriting of user statements.

**REC-04** — Completed tasks and feedback update future ranking inputs. Aggregates are computed from
eligible records, not editable profile numbers. Sparse histories show "new"/"few reviews"; absence of
reviews is not proof of poor skill. Seeded data demonstrates behaviour, not production accuracy.

**REP-01** — Either participant can report the other during negotiation, booking, or after completion.
Report = accessible category + description or voice note + optional evidence + linked interaction.
Categories: harassment, threats, impersonation concern, no-show, property/work issue, other. Private to
authorised staff and the reporter; **the reported participant cannot read the complainant's report.**

**REP-02** — Django Admin lists reports and verification cases with filters, evidence access controls,
recorded decisions. Report states: **open, reviewing, resolved, dismissed**. Staff can request
information, restrict new activity, suspend an account, or resolve with a reason. A complaint is not
proof; **AI does not issue punishments.**

**REP-03** — Reports remain possible for existing interactions after restriction. Users may block further
contact where feasible while preserving case records. New requests/invitations respect restrictions.
Staff retain required evidence per the documented retention policy.

**SAFE-01** — Exact customer addresses are not part of public discovery; revealed only within an accepted
booking to authorised participants. Before booking, use area and approximate distance. Customer consent
controls optional trusted-contact sharing. **No unstaffed "emergency response" promise or fake SOS.**

**SAFE-02** — Protect workers as well as customers: customer phone-confirmation state, participant-only
communication, reporting, clear job terms, restrictions on abusive accounts. A real launch needs an
operating review team and a defined identity/skills screening process.

---

## 9. Data model requirements

Use UUIDs or equivalent opaque external identifiers. Express invariants through **database constraints**
where possible and transactional service checks where cross-record logic requires them.

| Entity | Required information and relationships |
|---|---|
| User | Phone/login identity, role, language, active/restricted state, phone-confirmation method, demo flag |
| WorkerProfile | User, confirmed name/photo, declared experience, offered/excluded services, primary specialities, location precision, service coverage, accepting preference |
| Trade / ServiceTag / Area | Stable code, Urdu/English label, icon identifier, active state, trade relationship; bilingual question choices |
| VerificationCase | Worker, private evidence, OCR draft/confirmed fields, consent, method, status, provider reference, reviewer/time/reason, expiry, demo flag |
| JobRequest | Customer, original/confirmed description, category/tags, public area, private address, requested window, state, optional media |
| Invitation | Request, worker, status, opened/closed times and reason; identity separates repeated invitations |
| Message / Attachment | Invitation/booking, sender, audio/private file, transcript, approved description, interpretation state, client request ID, timestamps |
| QuoteVersion | Invitation, version, scope, item basis, money fields, material treatment, fee conditions, start/end window, expiry, state |
| AgreementGap | Quote version, source statements, type, unresolved/resolved status, confirmed resolution, actor/time |
| Booking | Job, worker, accepted quote snapshot/reference, agreed interval, state, idempotency key, timestamps and cancellation/dispute information |
| ChangeProposal | Booking, previous terms, proposed terms/version, approvals, status, timestamps |
| ArrivalCode | Booking, digest, expiry, attempt/issuance counters, used state; plaintext never in general booking responses |
| Review | Unique booking/customer, worker, 1–5 score, approved comment/audio, task tags, moderation state |
| Report / AuditEvent | Interaction, reporter/subject/category/evidence/status; actor, permitted action, target, reason and time |

**DATA-01** — Keep verification state, declared skill claims, review history, and availability distinct.
Never derive identity approval from OCR confidence, rating, or a worker-supplied profile field.

**DATA-02** — Record language, original input, confirmed interpretation, and relevant version for
consequential AI-assisted records. A later transcription change cannot silently alter an accepted
agreement.

---

## 10. API contracts and screen inventory

All APIs are prefixed **`/api/v1/`**. Errors are consistent and structured: **stable code, readable
message, field errors when applicable, request identifier.** Client translations use codes. The server
authorises every request independently of visible UI controls.

| Area | Planned endpoint families/actions |
|---|---|
| Foundation/accounts | health/live, health/ready, auth/csrf, auth/signup, auth/login, auth/logout, auth/me |
| Catalog | catalog/trades, catalog/service-tags, catalog/areas and trade-question choices |
| AI/media | audio/transcribe, audio/synthesise, interpretations; controlled private media upload/download |
| Worker | worker/profile, worker/verification, worker/availability, worker/invitations, worker/bookings |
| Customer/jobs | job-requests CRUD for owned drafts, confirm, recommendations, invite, withdraw invitation |
| Communication | invitation messages, quote versions, quotation-gap resolutions |
| Booking | quote acceptance with idempotency key; booking detail, arrive, issue arrival code, validate arrival code, request completion, confirm completion, cancel, raise issue |
| Changes/feedback | booking change proposals and approvals; eligible review creation; worker history |
| Moderation | report creation and reporter status; staff operations through Django Admin |

These are contract **families**. Before each module, document its exact request/response schema,
ownership rules, validation and error codes. **Never implement planned endpoints as fake successful
responses.**

### Required screens

Language/role selection; signup/login; worker voice introduction; private CNIC capture/status; speciality
questions; location/coverage confirmation; worker home and request list/detail; customer home and
request composer/confirmation; recommendation list and worker profile; conversation with quote composer
and gap prompts; accepted booking and arrival-code flow; completion/review; worker history; report
form/status; staff admin queues.

Each asynchronous screen handles **loading, empty, permission-denied, provider failure, offline/network
failure, and retry** states where applicable. Mock content must be visibly identified and must not look
like a successful live verification or AI response.

---

## 11. Security, privacy, reliability, and accessibility

- **SEC-01** — HTTPS in deployment, secure session cookies, CSRF for mutations, restricted hosts/origins,
  server-side object permissions, upload validation, rate limits for auth, uploads, AI, and codes.
  Client role checks are convenience only.
- **SEC-02** — Never expose CNIC numbers/images in public APIs, browser logs, analytics, URLs, crash
  reports, or unrelated AI prompts. Mask displayed numbers. Limit staff access; log evidence access
  without logging evidence contents.
- **SEC-03** — Consent notices for microphone, location, CNIC processing, cloud AI processing. Minimum
  required data by default. Explicit retention/deletion policy **before** collecting real identity
  documents; support deletion requests; explain records retained for active disputes.
- **SEC-04** — Secrets in environment variables; `.env.example` with placeholders; ignore secrets and
  private uploads in git; restrict production debug/admin access. **Do not log** raw voice, messages,
  passwords, OTPs, arrival codes, or provider credentials.
- **SEC-05** — Provider failures return actionable errors; persisted drafts survive retry. A local/offline
  screen must never imply a booking was confirmed without a server response. Re-fetch after uncertain
  mutations.
- **NFR-01** — Usable at 360 px width, keyboard-accessible core forms, labelled controls, logical focus,
  persistent language preference, Urdu shaping/RTL, readable code/money fields. Test on ≥ 2 phone/browser
  combinations.
- **NFR-02** — Limit audio duration and image sizes; paginate lists; avoid repeated interpretation charges
  for unchanged content. Explicit UI states for timeouts and latency. No unmeasured response-time or
  speech-accuracy guarantees.
- **NFR-03** — UTC timestamps, Asia/Karachi display, decimal money, immutable accepted agreements, audit
  history. Database state is authoritative across browser sessions.
- **NFR-04** — Distinguish production and demo modes at configuration, UI, and data level. **A production
  startup check rejects enabled simulated verification/authentication.** No private real-person data in
  seed files.

---

## 12. Acceptance and verification plan

| Test ID | Required observable result |
|---|---|
| AT-01 | Worker completes introduction, three icon questions and location confirmation in Urdu without needing English |
| AT-02 | Denied microphone/location and failed speech/OCR calls preserve progress and expose a usable fallback |
| AT-03 | OCR success leaves verification pending; only an authorised provider/staff action changes status with the correct method label |
| AT-04 | Pending, expired, rejected or suspended workers cannot receive new eligible bookings; demo approvals work only in demo mode |
| AT-05 | Customer confirms interpreted job, receives relevant workers, and invites one; other workers cannot read private details |
| AT-06 | Excluded speciality prevents an inappropriate match; new workers remain eligible and review counts are visible |
| AT-07 | Original voice and approved Urdu description are available; amount/date/material corrections survive reload |
| AT-08 | Conflicting material responsibility blocks acceptance until clarified and current terms explicitly accepted |
| AT-09 | A superseded or expired quotation cannot be booked; a later accepted change preserves prior terms in history |
| AT-10 | Two concurrent overlapping bookings for one worker produce one success and one conflict; a duplicate acceptance returns the existing booking |
| AT-11 | Non-overlapping scheduled windows are accepted; paused preference persists after completion; unfinished actual work blocks another start |
| AT-12 | Only the owning customer obtains the arrival code; wrong/expired codes and attempt limits work; success starts only the matching booking |
| AT-13 | Worker cannot complete unilaterally; customer can confirm or raise an issue; cancelled/noncompleted bookings cannot receive a review |
| AT-14 | Review is unique per completed booking; relevant task history updates recommendation inputs without fabricating credentials |
| AT-15 | Both roles can report an interaction; unrelated users and the reported user cannot read private report evidence |
| AT-16 | Private CNIC/audio/image URLs reject unauthorised requests; staff decisions and sensitive evidence access are audited |
| AT-17 | Frontend typecheck/build and relevant backend tests pass; local setup and deployed production-like flow work |

**AI evaluation** — 30–50 consented or fictional test utterances, several speakers: normal Urdu, mixed
trade vocabulary, noise, negation, amounts, ambiguous dates, corrections. Label expected fields
independently. Report field correctness and successful user actions; do not extrapolate production
accuracy from seeded demonstrations.

**Test strategy** — Automate permission boundaries, state transitions, money/quote validation,
uniqueness, idempotency, and **real PostgreSQL concurrency checks**. Manual phone testing for speech
quality, Urdu rendering, touch usability. Do not rely only on mocked unit tests for booking consistency
or external-provider correctness.

---

## 13. Module order and handoff rules

| Module | Implementation boundary and completion gate |
|---|---|
| **M1 Foundation** | New repository structure, Django/DRF/PostgreSQL, React/TS, custom user baseline, health checks, environment/config, docs; runnable backend/frontend |
| **M2 Accounts, language, catalog** | Session/CSRF auth, roles, demo-labelled phone adapter, Urdu/English shell and reusable audio/icon controls, seeded trade/service/area catalog |
| **M3 Audio and AI adapters** | Recording/upload, transcription, structured interpretation, TTS, private media, provider modes, schema validation, failure handling; actual sample tested |
| **M4 Worker onboarding** | Voice draft, private CNIC/OCR, verification adapter/admin queue, three speciality questions, location/coverage, eligibility and profile confirmation |
| **M5 Customer and job requests** | Accessible profile/signup assistance, voice/text request drafts, date/location confirmation, images and request ownership |
| **M6 Recommendations and invitations** | Eligibility/semantic matching, reasons, worker profiles, targeted invitations and worker inbox, decline/withdraw rules |
| **M7 Communication and agreements** | Private messages, approved Urdu descriptions, quote versions, gap detection/resolution, structured terms and read-aloud |
| **M8 Booking and arrival** | Atomic/idempotent acceptance, reservation windows, conflicts, cancellation, post-booking changes, arrival codes and start transition |
| **M9 Completion and feedback** | Completion/dispute states, unique eligible review, history/dashboard aggregates, task-specific ranking inputs |
| **M10 Reporting and moderation** | Both-sided reports, private evidence, restrictions, staff decisions, audit, safety and retention controls |
| **M11 Integration and delivery** | End-to-end testing, phone validation, provider evaluation, seed story, HTTPS deployment, README, backup demo and submission assets |

**Rules for every module prompt**

- Implement only the current module and dependencies it genuinely requires. Read the PDF and repository
  instructions first. Keep this summary and [progress.md](progress.md) current.
- Do not implement deferred features or silently expand scope.
- Before implementing, inspect existing code and identify exact API/schema changes. Reuse utilities,
  maintain contracts, create migrations when needed.
- Run the checks appropriate to the change; update docs with commands, results, limitations, provider
  modes. Do not stop at a plan or static mock if the module calls for working backend integration.
- At the end of each module report: what works, files changed, commands/checks run, known limitations,
  environment/keys needed for live capability, next module. **Never claim real NADRA, OTP, speech, or
  deployment success from a mock.**

---

## 14. Demonstration, delivery, and external dependencies

**Definition of done.** One customer and one worker complete the same persisted journey across two
sessions: worker voice onboarding, demo-labelled identity review, speciality/location confirmation,
spoken customer request, relevant recommendation, invitation, voice negotiation with a corrected
agreement gap, accepted quotation, arrival-code start, confirmed completion and feedback. Reporting is
demonstrated in a separate short action. Repeated or conflicting requests must preserve state.

**Seed data.** ~12 fictional workers across the three trades with varied services/exclusions, sample
areas, and an available / new / experienced / paused worker, plus explicitly labelled fictional
job/review histories. **Never seed an actual CNIC, phone number, home address, face photograph, or
private conversation.** Use visibly non-real identifiers and synthetic media.

**Repository documentation** must include setup, architecture and module progress, environment
variables, exact provider/model choices, all APIs/libraries/AI coding tools, seeded/mocked capabilities,
live-integration evidence, known limitations, tests, and deployment instructions. Keep code and private
uploads separate. Include a fresh-database setup path.

**Expo submission** requires a public source repository, a working live deployment, a ≤ 2-minute recorded
walkthrough, and a pitch deck. Deadline in the supplied rulebook: **28 November 2026, 11:59 PM**. Major
feature development freezes at submission; re-check the official rulebook before delivery. This document
does not itself establish competition eligibility.

### Provider selection and unresolved dependencies

- Choose and test speech, interpretation, OCR, and TTS providers early in M3. Support Urdu and actual
  target devices; do not assume browser-native recognition or Urdu synthesis exists everywhere. Short
  clips, cost limits, timeouts, fallback controls.
- NADRA institutional access, commercial terms, and applicant-binding method remain **unconfirmed**. Keep
  that adapter disabled for live verification until authorised access is implemented and tested.
- A real phone OTP provider, identity/skills screening operation, dispute reviewer, and retention policy
  are necessary before a real public pilot. The hackathon can demonstrate their clearly labelled
  boundaries.
- Speciality questions collect declarations, not trade tests. A later certification/assessment
  partnership may provide stronger skill evidence.

### Reference links named in the PDF

Capital Youth Expo hackathon rulebook; NADRA verification services; NAVTTC Recognition of Prior
Learning; Google Cloud Speech-to-Text language support; Gemini audio understanding; Azure speech
language support. These explain dependencies only — they do not imply partnership, approved access,
guaranteed accuracy, or a fixed price. No provider-specific SDK/version is mandated.
