# Kaam Madad · کام مدد

> **Name change:** this project was previously called *Roshan Rozgaar*. The requirements PDF still uses
> that name. Internal identifiers (database name/user `roshan_rozgaar`, Compose project/container
> `roshan-rozgaar`, the npm package name) intentionally keep the old name so existing setups keep working.

A mobile-first marketplace connecting customers with nearby skilled tradespeople (electricians, plumbers,
AC technicians). Workers must be able to complete the core journey **without understanding English**,
using Urdu text, spoken instructions, recognisable icons and guided choices.

Built for the Capital Youth Expo, Track 5 — Urdu & Regional Tech.

> **Status: Modules M1–M10 complete** (foundation; accounts, language, catalog; audio and AI adapters; worker
> onboarding and identity check; customer job requests; recommendations and invitations; private conversations
> and quotations; acceptance, booking and arrival; completion, disputes and reviews; reports and moderation).
> - A customer describes a job, invites a matching worker, agrees a structured quote and books the worker.
> - On the day the worker enters the customer's one-time arrival code. When the work is done, the worker asks
>   the customer to confirm.
> - The customer confirms and leaves one review, or raises an issue for staff.
> - Confirmed work and visible ratings then shape future recommendations.
> - Either person can privately report the other, or block further contact. Staff review reports in Django
>   Admin and can restrict or suspend accounts.
>
> Deployment and submission preparation are M11.
> See [docs/progress.md](docs/progress.md).
>
> **Pitch improvements (27 Nov 2026):**
> - ElevenLabs Scribe speech-to-text and Groq text AI (no Gemini key needed).
> - Answer the worker signup questions by voice, and "Listen to my choices".
> - Two-upload demo verification.
> - English requests reach Urdu-speaking workers with a customer-approved Urdu description.
> - The agreement check runs through Groq.
>
> See [Pitch configuration and rehearsal](#pitch-configuration-and-rehearsal-hackathon).

- Requirements: [docs/requirements.md](docs/requirements.md)
- Architecture and decisions: [docs/architecture.md](docs/architecture.md)
- API contracts: [docs/api.md](docs/api.md)
- Module progress, checks run, limitations: [docs/progress.md](docs/progress.md)

## Pitch configuration and rehearsal (hackathon)

The pitch runs on **ElevenLabs** for speech (Scribe speech-to-text and `eleven_v3` read-aloud) and **Groq** for text AI
(`openai/gpt-oss-120b` with strict JSON Schema output). **No Gemini key is needed.** Gemini stays selectable.

### Configure

In `.env` (see [.env.example](.env.example)):

```
SPEECH_TO_TEXT_PROVIDER=elevenlabs
TEXT_TO_SPEECH_PROVIDER=elevenlabs
INTERPRETATION_PROVIDER=groq
AGREEMENT_CHECK_PROVIDER=groq
ELEVENLABS_API_KEY=<key>
ELEVENLABS_VOICE_ID=<voice id>          # free plan: a premade voice, e.g. George JBFqnCBsd6RMkjVDRZzb
GROQ_API_KEY=<key>
```

Optional: `ELEVENLABS_STT_MODEL` (default `scribe_v3`), `ELEVENLABS_STT_URDU_FALLBACK_MODEL` (default `scribe_v2`),
`GROQ_MODEL` / `GROQ_INTERPRETATION_MODEL` / `GROQ_AGREEMENT_MODEL` (default `openai/gpt-oss-120b`),
`GROQ_INTERPRETATION_REASONING_EFFORT` (`low`), `GROQ_AGREEMENT_REASONING_EFFORT` (`medium`),
`GROQ_MAX_COMPLETION_TOKENS` (6000), `AI_PROVIDER_TIMEOUT_SECONDS` (20) and `AI_PROVIDER_MAX_RETRIES` (1).

- **ElevenLabs key permissions:** one key serves both uses. If the key's scope is restricted, enable **Text to Speech**
  (read-aloud) and **Speech to Text** (transcription). A key without Speech to Text access reports
  `ai_provider_not_configured` for transcription.
- **Urdu script:** in our live check `scribe_v3` wrote Urdu speech in Devanagari (Hindi script), even with
  `language_code=ur`. The adapter retries such a transcript once with `scribe_v2` + `language_code=ur`, which returned
  Urdu script with the English trade terms and the negation intact. If the result is still not Urdu script, it is
  refused and the user continues manually.
- **Keys stay on the server.** Only these go to providers: audio clips the user chose to transcribe (never report or
  dispute evidence), and text the user typed or approved. Addresses, access notes, photos, phone numbers and CNIC
  data are never sent.
- **Failures:** a quota error or outage keeps the user's input and offers the manual path. A failed automatic check
  shows as "could not run", never as a pass.
- **Re-use:** unchanged input is not sent twice (transcripts, suggestions and speech are re-used).

### Check the providers (prints no keys)

```bash
cd backend   # venv active
python manage.py check_ai_providers --only interpretation      # Groq: English job → Urdu description, signup by voice
python manage.py check_ai_providers --only agreement_check     # Groq: pitch example, revision, Roman Urdu, timing
python manage.py check_ai_providers --only text_to_speech --speak "کل شام دو پنکھے لگانے ہیں۔" --save-speech speech.mp3
python manage.py check_ai_providers --only speech_to_text --audio speech.mp3 --language ur   # Scribe
```

On Windows, set `PYTHONIOENCODING=utf-8` first so Urdu prints in the terminal. Each line says `[OK]` or `[FAIL]`
with the reason. The agreement check expects exactly one `materials_responsibility` finding for the pitch example,
none after the revision, one for Roman Urdu, and two (materials + timing) for the timing case.

### Rehearsal script (fictional data, about 6 minutes)

Before the rehearsal (from `backend/`): `python manage.py migrate`, `python manage.py seed_catalog`, then
`python manage.py seed_demo_workers`. Run `runserver` and `npm run dev`, and use three browser sessions: a worker,
a customer, and demo worker `03009990101` / `Demo-Worker-2026`.

1. **Worker signup (Urdu):** tap **مجھے کام چاہیے**, create the account (screen 1), then:
   - On screen 2, open **آواز سے جواب دیں** and say *"میں الیکٹریشن ہوں، پنکھے لگاتا ہوں اور wiring ٹھیک کرتا
     ہوں۔ میرا خاص کام پنکھے لگانا ہے۔ UPS کا کام نہیں کرتا۔"* The choices fill in, UPS goes under "not offered",
     and you check and save.
   - On screen 3, say *"اسلام آباد میں G-9 اور G-10، F-8 نہیں جاتا"*. Then tap **میرے انتخاب سنیں**.
2. **Demo verification:** after screen 3, choose **نمونے کی تصویر لیں** for the sample CNIC and the sample selfie,
   then **ڈیمو تصدیق مکمل کریں**. You should see "ڈیمو تصدیق مکمل ہو گئی۔". It is labelled as a demo with sample
   images, not NADRA.
3. **English job request:** as the customer, choose English and type (or say) *"Please install two ceiling fans in
   G-9 tomorrow evening. My budget is Rs. 1,200 including materials. No AC service needed."*
   - On the details screen, your own words stay as the description. Below them, check the **Urdu description for
     the worker**, edit it if needed, and tick the approval.
   - Pick the date and time, review, then confirm.
4. **Matching:** **Find a worker** lists the G-9 fan specialist `03009990101` first when the database holds only the
   seeded demo workers. Earlier fictional rehearsal workers with the same speciality tie with it. The paused demo
   worker is never listed. Invite `03009990101`.
5. **Worker side (Urdu):** as `03009990101`, open the invitation. The approved Urdu description comes first, and the
   original is marked English. **پڑھ کر سنائیں** reads the work, the Urdu description, the area and the time.
6. **Quote conflict:** the worker writes *"Rs. 1,200 is for labour only. You will buy the fans and wiring
   yourself."* and sends a quote: Rs. 1,200 total, materials supplied by the customer.
   - The automatic check shows **one** materials question.
   - Record a clarification (**Terms changed**). The worker replies *"OK, I will bring the materials. Rs. 1,200
     including materials."* and sends a revised quote with materials included.
   - The check comes back with **no findings**, and the quote is ready for the customer to accept.

Without keys (development fixtures), the same flow runs and every simulated result is labelled "Simulated result".
In fixture mode the Urdu description is assembled from catalog labels, not translated.

## Stack

Django 6.1 + Django REST Framework · PostgreSQL 18 · React 19 + TypeScript 7 + Vite 8 + Tailwind CSS 4.
Sessions with HttpOnly cookies and CSRF; in production Django serves the API, admin and built frontend from
one origin. Full version list: [docs/architecture.md](docs/architecture.md#1-stack-resolved-versions-m1).

## Prerequisites

- Python **3.12+** (tested 3.14)
- Node.js **22.22+** (tested 24.12) and npm
- **Either** Docker Desktop / Docker Engine with Compose **or** an existing PostgreSQL 14+ server
- **Tesseract OCR 5.x** with English language data for the CNIC scan (M4). Install steps:
  [§7](#install-tesseract-ocr-card-scanning-runs-on-this-machine). Everything else works without it.

No provider keys are required to run the app. Optional speech/AI keys are covered in §6; OTP and NADRA are not
integrated (see [Integrations not available yet](#integrations-not-available-yet)).

## 1. Configure

From the repository root:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Edit `.env` and set at least `POSTGRES_PASSWORD` (any local value). Every variable is explained in
[.env.example](.env.example). Keep `POSTGRES_HOST=127.0.0.1` (not `localhost`; see the note in the file).

## 2. Database

### Option A — Docker Compose (recommended)

```bash
docker compose up -d db        # PostgreSQL 18 on 127.0.0.1:5434
docker compose ps              # wait for "healthy"
```

The host port defaults to **5434** to avoid clashing with a local server on 5432 or other projects on
5433; change `POSTGRES_PORT` in `.env` if needed. Data lives in a named volume.
`docker compose down -v` deletes it (fresh database).

**Troubleshooting**
- `failed to connect to the docker API ... dockerDesktopLinuxEngine`: Docker Desktop is not running. Start it
  and wait for "Engine running".
- `password authentication failed for user "roshan_rozgaar"`: `POSTGRES_PASSWORD` in `.env` was changed after
  the database was first created (PostgreSQL stores the password only on first start). Keep your data and
  apply the new password with (Linux/macOS/Git Bash):
  ```bash
  docker exec -i -e NEWPW="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)" roshan-rozgaar-db-1 \
    sh -c 'psql -q -U roshan_rozgaar -d roshan_rozgaar -v pw="$NEWPW"' <<< "ALTER ROLE roshan_rozgaar PASSWORD :'pw';"
  ```
  Or, if the local database holds nothing you need: `docker compose down -v` then `docker compose up -d db`
  and `python manage.py migrate` (this deletes all local data).

### Option B — Existing PostgreSQL server

Create a role and database (the role needs `CREATEDB` so the test runner can create its test database):

```sql
CREATE ROLE roshan_rozgaar WITH LOGIN PASSWORD 'choose-a-password' CREATEDB;
CREATE DATABASE roshan_rozgaar OWNER roshan_rozgaar;
```

Then set `POSTGRES_HOST`, `POSTGRES_PORT` (usually `5432`), `POSTGRES_DB`, `POSTGRES_USER` and
`POSTGRES_PASSWORD` in `.env` to match.

## 3. Backend

```powershell
# Windows PowerShell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate              # also creates the rate-limit cache table
python manage.py seed_catalog         # trades, services, sample areas, speciality questions (safe to re-run)
python manage.py check_ai_providers   # optional: shows which AI/audio providers are active
python manage.py createsuperuser      # optional staff login: phone e.g. 03001234567 (no spaces), then a password
python manage.py runserver 127.0.0.1:8000
```

```bash
# Linux / macOS
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate              # also creates the rate-limit cache table
python manage.py seed_catalog         # trades, services, sample areas, speciality questions (safe to re-run)
python manage.py check_ai_providers   # optional: shows which AI/audio providers are active
python manage.py createsuperuser      # optional staff login: phone e.g. 03001234567 (no spaces), then a password
python manage.py runserver 127.0.0.1:8000
```

`seed_catalog` matches records by stable code: re-running it creates nothing new, refreshes labels of known
entries, keeps staff deactivations, and never deletes staff-created entries. Use `--dry-run` to preview.

If PowerShell blocks `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call `.\.venv\Scripts\python.exe` directly.

Login identity is a **Pakistani mobile number**; any common format is accepted and stored as
`+923XXXXXXXXX`. Use fictional numbers for local accounts.

## 4. Frontend

In a second terminal:

```bash
cd frontend
npm ci            # installs exact versions from package-lock.json
npm run dev       # http://localhost:5173
```

Open **http://localhost:5173**. Vite proxies `/api`, `/admin` and `/static` to Django on port 8000, so the
browser sees one origin. Staff admin: **http://localhost:5173/admin/** (or http://127.0.0.1:8000/admin/).
To change the proxy target, copy `frontend/.env.example` to `frontend/.env.local`.

To open the dev site from a phone on the same network: `npm run dev -- --host`, and add the computer's LAN
IP to `DJANGO_ALLOWED_HOSTS` and `http://<ip>:5173` to `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env`.

## 5. Using the app (M2, updated in M4)

Local development runs as a **demo deployment** (`APP_DEPLOYMENT_MODE=demo`): every screen shows a demo banner
and new accounts are marked as demo accounts. Use fictional phone numbers.

**Create a worker and a customer**
1. Open http://localhost:5173 and tap **مجھے کام چاہیے / I need work** or **مجھے کاریگر چاہیے / I need a worker**.
   The role is preselected on the signup screen. Use the header button to switch language.
2. Enter a mobile number (any format, e.g. `0300 1234567`) and a password (8+ characters, not only digits,
   not a common password) twice → **Create account**.
   - Workers continue to onboarding screens 2 and 3 (see §7).
   - Customers land on their dashboard.
   - Phone confirmation is offered on both dashboards.
3. Log out (header button) and repeat with another number and the other role.

**Log in**: **Log in** on the landing page, phone number + password. Workers land on `/worker`, customers on
`/customer`; opening the other role's page redirects to your own home. Sessions survive page reloads for 14 days.

**Demo phone confirmation**: on the phone-confirmation screen press **Get a demo code**. No SMS is sent — the
code appears in a box labelled "Demo code — not sent by SMS". Enter it and press **Confirm**. The account then
shows **"Demo confirmation (not real verification)"**. Codes expire after 10 minutes, allow 5 wrong attempts,
can be re-requested after 60 s, and at most 5 times per hour. Phone confirmation never verifies legal identity or
skills.

**Switch languages**: the header button shows the other language (**English** / **اردو**). Signed out, the
choice is remembered on the device. Signed in, it is also saved to your account; after any login the account's
saved language is applied.

**Catalog**: http://localhost:5173/catalog shows trades, their services, the three speciality questions and the
sample areas from the API. Staff manage the catalog at `/admin/` (Service catalog section).

### Integrations not available yet

| Capability | Status |
|---|---|
| SMS / OTP delivery | **Not integrated.** Demo mode simulates codes (no SMS). With `PHONE_VERIFICATION_PROVIDER=unconfigured` the app honestly says SMS confirmation is unavailable. Live mode refuses to start with the demo provider. |
| CNIC OCR | **Implemented** (M4): local Tesseract on the backend host (no external service). Reads the printed English name and number. |
| NADRA / identity verification | **Not integrated** (needs authorised access). Demo deployments use a **two-upload demo verification** with sample images (the M4 card scan + fictional registry is still at `/worker/verify/card`); demo approvals never count in live mode. |
| Speech-to-text, interpretation, text-to-speech | **Implemented** (M3, pitch update): speech-to-text with ElevenLabs Scribe (`scribe_v3`, with a `scribe_v2` Urdu-script fallback) or Gemini; interpretation with Groq (`openai/gpt-oss-120b`) or Gemini; read-aloud with ElevenLabs `eleven_v3` or Azure AI Speech. All selectable. Need keys in `.env`; without them development uses labelled fixtures and production reports "not configured". See [Pitch configuration](#pitch-configuration-and-rehearsal-hackathon). |
| Customer job requests | **Implemented** (M5): voice/text description, review, confirmation, private photos |
| Recommendations and invitations | **Implemented** (M6): rule-based matching with reasons, one active invitation per request |
| Conversations, quotations, agreement check | **Implemented** (M7): private text and voice-note messages, structured versioned quotes, agreement check (Groq, Gemini or a labelled demo fixture) |
| Acceptance, bookings, arrival codes | **Implemented** (M8): booking from an accepted quote, no double-booking, one-time arrival code, cancellation and changes |
| Completion, disputes, reviews | **Implemented** (M9): customer-confirmed completion, staff dispute outcome in Django Admin, one review per completed job (typed or voice draft), work history in recommendations |
| Misconduct reports and moderation | **Implemented** (M10): private reports with evidence, staff queue with audited decisions in Django Admin, restrictions, contact blocking, evidence retention command |

## 6. Voice and AI (M3)

Open **http://localhost:5173/voice-test** while signed in (link "Voice test (preview)" on both home pages).
Flow: choose *Worker introduction* or *Job description* and the spoken language → **Record** (or **Upload a
voice file**) → replay → **Write it down** → review the original transcript and correct the extracted fields →
**Confirm** → **Read aloud**. **Type instead** skips recording. Nothing is published from this page.

- **Recording** uses the browser microphone (permission is asked only when you press Record), stops at
  60 seconds, and produces 16 kHz mono WAV. It needs `https://` or `localhost`; a phone opening the dev server
  as `http://<LAN-IP>:5173` cannot record (browser rule), but can upload a file or type.
- **Uploads**: WAV, MP3, M4A (AAC), AAC, OGG (Opus/Vorbis, e.g. WhatsApp voice notes), FLAC; at most 60 s and
  10 MB. The server checks the actual file content and duration. WebM is not accepted.
- **Local development uses fixtures**: transcripts, drafts and speech are deterministic *simulated* results
  labelled "Simulated result (not real AI)". The fixture transcript is a fixed fictional sample (it does not
  listen to your audio); read-aloud plays a test tone, not speech.

### Live check with real providers

1. Get a **Gemini API key** at https://aistudio.google.com/apikey and an **Azure AI Speech** resource
   (key + region, e.g. `centralindia`) from the Azure portal.
2. In `.env` set:
   ```
   SPEECH_TO_TEXT_PROVIDER=gemini
   INTERPRETATION_PROVIDER=gemini
   TEXT_TO_SPEECH_PROVIDER=azure
   GEMINI_API_KEY=<your key>
   AZURE_SPEECH_KEY=<your key>
   AZURE_SPEECH_REGION=<your region>
   ```
3. Record a **fictional** sample (no real names, CNIC or addresses), e.g. in Urdu:
   *"میرا نام احمد ہے۔ میں الیکٹریشن ہوں۔ میں پنکھے لگاتا ہوں لیکن motor rewinding نہیں کرتا۔"*
   Save it as WAV or M4A (≤ 60 s).
4. From `backend/` (venv active): `python manage.py check_ai_providers --audio path\to\sample.wav --language ur`.
   Each step prints `[OK]` with the result or `[FAIL]` with `ai_provider_not_configured`,
   `ai_provider_limit_reached`, `ai_provider_unavailable` or `ai_output_invalid`. No keys are printed.
5. Expected: the transcript keeps *motor rewinding* and *نہیں*; the draft offers fan installation and lists
   "motor rewinding" as unmatched and **negated**; text-to-speech returns WAV from `ur-PK-UzmaNeural`.
6. Restart `runserver` and repeat the flow at `/voice-test`; `GET /api/v1/config/` should show
   `"simulated": false, "available": true` for all three. If interpretation reports `ai_output_invalid`
   (`no_text_output`), the Gemini response shape differs from the documented forms — see
   [docs/architecture.md §9](docs/architecture.md#9-module-m3--audio-and-ai-adapters).

### Read-aloud with ElevenLabs (`eleven_v3`)

Read-aloud can use ElevenLabs instead of Azure. Speech-to-text and interpretation are not affected: they keep
whatever `SPEECH_TO_TEXT_PROVIDER` / `INTERPRETATION_PROVIDER` you set (Gemini or the fixtures).

1. In ElevenLabs, create an API key (Developers → API keys, with *Text to Speech* access) and copy a **voice ID**
   from *My Voices*. On the **free plan use a premade/default voice** (e.g. George `JBFqnCBsd6RMkjVDRZzb`):
   free accounts cannot use Voice Library voices through the API (`paid_plan_required`). `eleven_v3` reads Urdu
   and English with the same voice.
2. In `.env` set:
   ```
   TEXT_TO_SPEECH_PROVIDER=elevenlabs
   ELEVENLABS_API_KEY=<your key>
   ELEVENLABS_VOICE_ID=<voice id>
   ```
   Optional: `ELEVENLABS_MODEL_ID` (default `eleven_v3`), `ELEVENLABS_OUTPUT_FORMAT` (default `mp3_44100_128`;
   `mp3_*` or `wav_*` only), `ELEVENLABS_ZERO_RETENTION=true` (enterprise accounts only).
3. Check it from `backend/` (venv active) with a **fictional** sentence and listen to the file:
   ```
   python manage.py check_ai_providers --only text_to_speech --save-speech speech.mp3
   python manage.py check_ai_providers --only text_to_speech --speak "کل شام دو پنکھے لگانے ہیں۔ AC کی service نہیں چاہیے۔" --save-speech speech.mp3
   ```
   Expected: `[OK] text_to_speech: elevenlabs voice=eleven_v3/<voice id> simulated=False format=audio/mpeg …`
   and a playable `speech.mp3`. `[FAIL]` lines show the reason: `missing_api_key`, `missing_voice_id`,
   `credentials_rejected`, `voice_not_found`, `paid_plan_required` (not configured), `quota_exceeded` or
   `too_many_concurrent_requests` (usage limit), `system_busy` or `http_<status>` (provider failure).
4. Restart `runserver`, open `/voice-test`, type or record a fictional sentence, **Confirm**, then **Read aloud**.
   The page does not show the "simulated" label, and `GET /api/v1/config/` shows
   `"text_to_speech": {"provider": "elevenlabs", "available": true, "simulated": false}`.

Privacy note: ElevenLabs keeps generated speech in the account's history unless zero-retention mode is used
(enterprise only). Only confirmed draft text is sent, never audio or transcripts, but use fictional text for tests.

Fixture results are refused in a live deployment: production settings with `APP_DEPLOYMENT_MODE=live` and any
`*_PROVIDER=fixture` fail at startup.

## 7. Worker onboarding and identity check (M4)

### Install Tesseract OCR (card scanning runs on this machine)

CNIC photos are read by the **Tesseract** program on the Django host. No external OCR service is used.

**Windows**

```cmd
winget install --id UB-Mannheim.TesseractOCR --exact
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
"C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

The installer includes the `eng` language data and does not add Tesseract to PATH. The backend also looks in
`C:\Program Files\Tesseract-OCR\tesseract.exe` automatically. For any other location, set `TESSERACT_CMD` in `.env`.

**Linux (Debian/Ubuntu)**

```bash
sudo apt install tesseract-ocr tesseract-ocr-eng
tesseract --version && tesseract --list-langs
```

`--list-langs` must include `eng` (or whatever `TESSERACT_LANG` names). Optional settings in `.env`:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe   # or /usr/bin/tesseract; default: "tesseract" on PATH
TESSERACT_LANG=eng
OCR_TIMEOUT_SECONDS=20
```

If Tesseract is missing, the verification screen shows a setup error. The onboarding screens and the dashboard
keep working without it.

### Update an existing checkout

From `backend/` (venv active):

```cmd
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_catalog
python manage.py seed_demo_registry
python manage.py check_ai_providers --only cnic_ocr --cnic-image ..\docs\demo\cnic\demo-card-bilal-ahmed.png
```

- `pip install` adds **Pillow** for photo checks.
- `seed_catalog` sets the main speciality to exactly one.
- `seed_demo_registry` loads the fictional registry. It is idempotent and refused in live mode.
- The last line should print `[OK] cnic_ocr: … status=read name='Bilal Ahmed' number=*****-*****67-1`.

### Demo: worker

1. Open http://localhost:5173 and tap **مجھے کام چاہیے / I need work**.
   - **Screen 1:** mobile number and password, with a play button for the password instruction.
   - **Screen 2:** trade, the services offered, then **one** main speciality. Services not offered are under
     **More options**.
   - **Screen 3:** a city and the areas the worker will travel to.
   - No microphone, location permission or CNIC is needed. Each screen is saved, so a refresh or a later
     login resumes at the right screen.
2. The **dashboard** is usable straight away. It shows profile completion, identity status and the
   "accepting requests" choice separately, and explains why the worker cannot take jobs yet.
3. **Demo verification (event default, pitch update):** after screen 3, or later from **Verify identity to take
   jobs**, the worker adds a **sample CNIC** and a **sample selfie**. **Use the sample image** loads the fictional
   samples from `frontend/public/demo-samples/`.
   - The server checks both only as images (type, ≤ 5 MB, ≥ 400 × 250 px). It runs no OCR, face matching or
     registry lookup, keeps nothing, and sends nothing to a provider.
   - It records the existing demo approval and shows "Demo verification complete".
   - It is refused outside demo mode, and it is not NADRA verification.
4. **Card scan (M4, optional):** open `/worker/verify/card` for the earlier flow:
   1. Give consent.
   2. **Take a photo** or **Upload a photo** of a DEMO card from [`docs/demo/cnic/`](docs/demo/cnic/).
   3. Check the name and number Tesseract read, correct them if needed, and submit.

| Card | What happens |
|---|---|
| `demo-card-bilal-ahmed.png`, `demo-card-sana-tariq.png`, `demo-card-imran-siddiqui.png` | Read → submit → **"Demo identity check passed. Name and CNIC number matched our demo registry."** with a labelled **Demo address** |
| `demo-card-wrong-name.png` | Bilal Ahmed's number with the name "Kamran Shah" → **name does not match** → correct the name to `Bilal Ahmed` → passes (recorded as a correction) |
| `demo-card-unknown-number.png` | Number `00000-9999999-9` → **no demo record** |
| `demo-card-unreadable.jpg` | Blurred → **nothing could be read** → retake, or type the details |
| `demo-card-sana-tariq-rotated.jpg` | Sideways phone photo → turned and read |
| `demo-card-imran-siddiqui-lowquality.jpg` | Small, soft, low contrast → number read, name left blank → type `Imran Siddiqui` |

Photos are not stored: they are checked (type, ≤ 5 MB, ≥ 400 × 250 px), read in a temporary folder that is
then deleted, and only the masked number (`*****-*****67-1`) is kept. Demo approvals count **only** when
`APP_DEPLOYMENT_MODE=demo`. In a live deployment the demo registry is refused at startup, and NADRA access
stays unconfigured.

### Demo: customer

Tap **مجھے کاریگر چاہیے / I need a worker** and enter your mobile number and password on one screen. You land
on the customer dashboard, where phone confirmation is available. Job requests (and their service area) come
in M5.

## 8. Customer job requests (M5)

After pulling: `python manage.py migrate` (adds the `jobs` app). Nothing else is new to install.

### Demo: customer

1. Open http://localhost:5173 and tap **مجھے کاریگر چاہیے / I need a worker**. Sign up (one screen) to reach
   the **customer dashboard**, which has **Describe your job** and **My requests**.
2. **Step 1, describe:** choose Urdu or English, then either
   - **Speak**: record (permission is asked only when you press Record) or **upload** a voice file, or
   - **Type**.

   **Continue** saves a **draft first**, then asks the AI for suggestions. If transcription or AI fails, the
   draft is kept: **Try again**, **Continue without suggestions**, or **Start over**.
3. **Step 2, details:**
   - **What you said** is your original words (never changed).
   - Choose the trade and the work; work you do **not** need is under **More options**. Then the city and area.
   - Pick the **date, start and end time** (Pakistan time). If you said "کل شام", the screen shows the phrase
     and asks you to pick the actual times; it never guesses them.
   - Optional: the exact address and access notes (private), a budget (your preference, not a price) and up
     to 5 photos.
   - **Save draft** or **Save and review**. Drafts can be reopened from **My requests**, even after a reload.
4. **Step 3, review:**
   - A plain summary. **Read aloud** reads only the work, area, date and time, never your address or notes.
   - **Confirm request** saves it. It does **not** invite a worker or reserve a time.
   - You land on the request page, which you can reopen from **My requests**.

With the default development settings (`*_PROVIDER` not set) voice and AI are **simulated fixtures**, and say so
on screen. The fixture transcript is a fixed sample: "…G-9 … کل شام کو آ جائیں۔ AC کی service نہیں چاہیے". To use
real providers, see §6.

### Rules the server enforces

- **Catalog:** services must belong to the chosen trade, the area must belong to the chosen city, and
  needed and not-needed work cannot overlap.
- **Time window:** the end must be after the start, the start cannot be in the past or more than 90 days ahead,
  and times are stored in UTC.
- **Photos:**
  - JPEG/PNG/WebP, ≤ 5 MB, ≤ 5 per request, checked by content.
  - Re-saved **without metadata**, so GPS is removed.
  - Downloads only for the owner. Photos never go to AI.
- **Access:** only the owner can see, edit, confirm or download a request; workers cannot browse requests in M5.
- **Confirming:** confirming twice keeps **one** confirmed request, and a failed confirmation leaves the draft
  as it was.

## 9. Recommendations and invitations (M6)

After pulling, from `backend/`: `python manage.py migrate` (adds the `invitations` app), then
`python manage.py seed_demo_workers`.

The seed command creates or resets four **fictional** demo workers, all with the password `Demo-Worker-2026`
(demo mode only):

| Phone | Trade | Main speciality | Areas | Notes |
|---|---|---|---|---|
| 03009990101 | Electrician | Ceiling fan installation | G-9, G-10, F-8 | Recommended for fan jobs in G-9 |
| 03009990102 | Electrician | Switch and socket repair | G-9, I-8 | Offers fan installation, ranked after main-speciality matches |
| 03009990103 | Plumber | Leak repair | G-10, Saddar (Rawalpindi) | |
| 03009990104 | Electrician | Ceiling fan installation | G-9 | **Paused** (not accepting requests), so never listed |

### Demo: invite a worker

1. **As a customer**, create and confirm a request (§8). For example: electrician, ceiling fan installation, G-9.
2. On the confirmed request, tap **Find a worker / کاریگر تلاش کریں**. The list shows matching workers, why each
   one matches (listed speciality, offers the work, serves your area), a clearly labelled demo identity check,
   and "new worker".
3. Tap **Invite** on a card to see **exactly what the worker will see** and what is not shared (address, access
   instructions, photos, recording, phone).
   - If the description looks like it contains a phone number or an address, you are warned and can edit it
     before sending.
   - Tap **Send invitation**. The page shows the open invitation and whether the worker has seen it. A refresh
     keeps that state.
4. **As the worker**, in another browser or a private window, log in as `03009990101` / `Demo-Worker-2026`.
   - The dashboard shows **Job invitations**. Open one to see the work, area, requested time and description,
     and **read it aloud**.
   - **Decline**, optionally with a reason.
5. **Back as the customer**, refresh. The invitation is declined (under history) and the slot is free: invite
   another worker. **Withdraw invitation** also frees the slot. Inviting again always creates a new invitation.

Rules: one open invitation per request; a different worker cannot be invited while one is open
(`invitation_already_active`); a worker who paused or lost eligibility after being listed cannot be invited.
An invitation does **not** book the worker or reserve time.

## 10. Conversations and quotations (M7)

After pulling, from `backend/`: `python manage.py migrate` (adds the `conversations` app). Demo workers come from
`python manage.py seed_demo_workers` (§9).

### Demo: talk, quote, clarify

1. **As a customer**, invite demo worker `03009990101` (§9). On **Find a worker**, the open invitation now has
   **Open conversation / بات چیت کھولیں**. Write a message and send it.
2. **As the worker** (another browser or a private window), open the invitation and tap
   **Talk to the customer and send a quote**.
   - New messages appear within about 5 seconds. Anything you are typing is kept.
   - **Speak** → record or upload a voice note → **Prepare caption**. Check and correct the Urdu caption; the
     other person reads exactly that text. If no caption can be made, you can type one or send the voice note
     with "Caption unavailable".
3. **Prepare a quote** as the worker: what the work covers, whole-job or per-item labour, who supplies the
   materials, any visit or inspection fee, what is not included, and the proposed time (Pakistan time).
   - An amount you don't know yet can be left empty. It shows as "not known yet" and is never counted as zero.
   - **Send quote**. A sent version cannot be changed; **Send a revised quote** creates the next version, and
     earlier versions stay under "Earlier versions".
4. Both people see the same quote, with **Read aloud** in Urdu or English, and the **automatic check**.
   - Example conflict: the request says *"1200 روپے سامان سمیت"* (materials included), but the quote says the
     customer supplies the materials.
   - The check shows the exact statements that disagree, a short question, and who should answer.
   - Clarify in the chat, then record what was agreed under **Save clarification**; a note is required.
     - **Existing quote terms confirmed**: the version as written is right, so the point is resolved.
     - **Terms changed**: price, work, materials or time differ. This version stays blocked until the worker
       sends a revised quote.
5. When nothing blocking is left, both see **Ready for customer acceptance**. Accepting it is in §11.
6. If the customer withdraws (or the worker declines), the conversation stays readable from the invitation
   history (**View conversation**), but nothing new can be sent.

In demo mode the automatic check is a **labelled simulation** ("Simulated result (not real AI)"). It uses keyword
rules for the materials example only.

**Live check with Gemini:** set `AGREEMENT_CHECK_PROVIDER=gemini` in `.env` (the key is the same
`GEMINI_API_KEY`), restart, and run `python manage.py check_ai_providers --only agreement_check`. If the checker
cannot run, the quote shows **"The automatic check could not run"**, never a pass. The customer can then try again
or confirm they compared the quote themselves.

### Rules the server enforces

- Only the customer and the invited worker can read, play or write. Anyone else gets "not found".
- Messages cannot be edited or deleted. A send that is retried with the same device-generated ID is stored once.
- Quotes are structured and their totals are computed on the server. A version expires after 24 hours or at its
  start time, whichever comes first.
- Sending a quote and closing the invitation are serialised. A quote can never be sent after the invitation
  closed.
- The automatic check receives the shared request summary, approved message texts and the quote terms only. It
  never receives the address, access notes, photos, audio or phone numbers.

## 11. Accepting a quote, booking and arrival (M8)

After pulling, from `backend/`: `python manage.py migrate`. This adds the `bookings` app and enables the
PostgreSQL `btree_gist` extension, which the no-overlap constraint needs; the Docker database user is allowed to
create it.

### Demo: book, arrive, start

1. **Customer:** in the conversation (§10), once the quote is ready, tap **Review and accept this quote / قیمت
   دیکھیں اور منظور کریں**.
   - The screen shows the version, the agreed time, the known charges, what is still unknown, and what happens
     next.
   - **Accept and book** opens the booking.
   - If the connection drops, the app first checks whether the booking went through. Trying again cannot book
     twice.
2. **Worker:** **My bookings** on the dashboard → open the booking.
   - The customer's exact address and access notes now appear here, and only here.
   - On the day: **I have arrived**.
3. **Customer:** the booking shows the arrival.
   - Check that it is the booked worker (trade, reference and identity status are shown), then **Show the
     arrival code**.
   - The 6-digit code is shown once and is valid for 15 minutes. **Get a new code** replaces it.
4. **Worker:** enter the code and tap **Start work**.
   - A wrong code shows how many attempts are left (5 in all).
   - The right code moves the booking to **In progress**.
5. **Changes** (for example a third fan): either person can **Propose a change**. The other sees "now / proposed"
   and approves or rejects. The terms in effect change only after both agree, and the original agreement stays
   visible.
   - The time can be changed only before the worker arrives, and only to a free slot.
6. **Cancel** (before the work starts): either person, with a reason.
   - The worker's time is freed, and the invitation and its quote are closed.
   - The customer can invite someone again from the request.

### Rules the server enforces

- **Acceptance:**
  - One customer-only action for one exact quote version, with an idempotency key.
  - Locks are taken in a fixed order (job → invitation → quote → worker), and every condition is re-checked
    under those locks. Stale, expired or blocked quotes get a clear `409` with the current state.
- **No double-booking:** a worker's open bookings can never overlap. Back-to-back slots are fine. PostgreSQL
  enforces this too.
- **One job at a time:** a worker cannot start a second job while one is in progress, even if the planned times
  do not overlap.
- **After booking:**
  - The quote and its approval record no longer change.
  - No new invitations or quote versions, and withdraw/decline point to the booking.
  - Messages continue.
- **Arrival codes:**
  - Created with secure randomness; only a keyed digest is stored.
  - Shown only to the customer, only once; never sent in any worker response, log or read-aloud.
  - 15 minutes, 5 wrong attempts, rate-limited.
  - A code confirms arrival for this booking only. It is not an identity, location, skills or safety check.

## 12. Completion, disputes and reviews (M9)

After pulling, from `backend/`: `python manage.py migrate` (adds the `reviews` app and the new booking states).

### Demo: complete, review, see the history

1. Take a booking to **In progress** (§11).
2. **Worker:** on the booking, tap **Ask the customer to confirm completion / گاہک سے تکمیل کی تصدیق مانگیں**.
   - If a change is still waiting for a decision, the button is disabled with an explanation. Decide or withdraw
     the change first.
3. **Customer:** the booking shows **Is the work done as agreed?**
   - **Yes, confirm completion** marks it completed and frees the worker's time.
   - Then **How was the work?** asks for 1–5 stars and an optional text. Under **Say it instead of typing**,
     record or upload a voice note and tap **Write it down for me**. Check and edit the Urdu draft, then **Send
     review**. There is one review per job.
4. **Worker dashboard:** **My bookings** is grouped into awaiting confirmation, issues, booked and in progress,
   completed, and cancelled or closed. **My work history** shows completed jobs, the rating with its review count,
   and each job's feedback.
5. **Recommendations:** the customer creates a new request for the same service and opens **Find a worker**.
   - The worker's card now says how many confirmed jobs included that service, with the rating and count.
   - The worker ranks above otherwise equal workers. Workers without reviews show "No reviews yet", not a zero.

### Demo: an issue instead of confirmation (staff outcome)

1. At step 3, choose **No, there is an issue**, pick a reason and write a short note. The booking becomes
   **Issue raised**.
   - The worker stays booked and cannot start another job, even after the planned end.
2. **Staff:**
   - Create a staff account with `python manage.py createsuperuser`, or give a staff user the
     "Can record the outcome of a booking dispute" permission.
   - Open `/admin/` → Bookings → the booking → **Record dispute outcome**. Choose **Returned to in progress** or
     **Closed without confirmed completion** and give a reason.
   - A closed booking frees the worker, does not count as completed work, and cannot be reviewed.
3. **Hiding a review:** `/admin/` → Reviews → a review → **Hide review…** with a reason. This needs the
   "Can hide an abusive review" permission. The text is kept; the worker's rating and count update.

## 13. Reports, moderation and blocking (M10)

After pulling, from `backend/`: `python manage.py migrate` (adds `reports`, the account restriction field and the
`report` audio purpose).

### Demo: report → staff → resolution

1. **Report (customer or worker):** in a conversation or on a booking, open **Safety → Report a concern /
   شکایت درج کریں**.
   - Choose what happened, then describe it or record a voice note (one of the two is required). Optionally add
     up to 5 photos; location and camera details are removed.
   - Send. The report opens with status **Open**. It is also under **My reports** on both dashboards.
   - The other person is not told and cannot open it. A report does not cancel or change a booking.
2. **Staff:**
   - Create fictional staff with `python manage.py createsuperuser` (all permissions), or give a staff user only
     the permissions they need:

     | Permission | Allows |
     |---|---|
     | "Can review reports and record decisions" | The queue and **Record a decision…** |
     | "Can open report evidence" | Opening evidence; every opening is recorded |
     | "Can restrict, suspend or lift restrictions" | Account actions on the reported account |

   - Open `/admin/` → **Reports**. Filter by status, category or date. Open a report: it shows the text, links to
     the invitation and booking, the evidence ("Open (recorded)"), the messages and the decision log.
   - **Record a decision…**: choose **Ask the reporter for more information**, write the reason (staff only) and
     the message the reporter should see. An internal note is optional and never shown to users.
3. **Reporter:** the report shows **Staff asked for more information** with the staff message. Reply in the box.
4. **Staff:** **Record a decision…** → **Resolve** (or **Dismiss**), with a message to the reporter.
   - Optionally add an account action: **Restrict** (sign-in still works, but no new requests, invitations,
     messages, quotes or bookings), **Suspend** (no login), or lift either. A reason is required, and everything
     is audited.
5. **Block:** under Safety, **Block further contact** stops new messages, quotes, invitations and bookings
   between the two, in both directions. History and any existing booking stay. Only the person who blocked can
   allow contact again.

### Evidence retention (prototype)

`python manage.py purge_report_evidence --dry-run`, then run it without `--dry-run`.
- It removes the photos and recordings of reports resolved or dismissed more than
  `REPORT_EVIDENCE_RETENTION_DAYS` days ago (default 180).
- It never touches open cases or bookings still awaiting completion or disputed.
- Reports, decisions and the evidence-access log are kept.

## 14. Checks and tests

```bash
# Backend (from backend/, venv active) — runs against a real PostgreSQL test database
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --settings=config.settings.test   # "manage.py test" now defaults to these settings

# Frontend (from frontend/)
npm run typecheck
npm test
npm run build      # typecheck + production build into frontend/dist
```

Health endpoints:

```bash
curl http://localhost:5173/api/v1/health/live/    # {"status":"ok"}
curl http://localhost:5173/api/v1/health/ready/   # {"status":"ok","checks":{"database":"ok"}} or 503
```

## 15. Production-like local run (same origin)

Builds the frontend and lets Django serve everything on one port, with production settings
(HTTPS redirect disabled only because this local test uses plain HTTP):

```powershell
# Windows PowerShell (frontend built first: cd frontend; npm run build)
cd backend
$env:DJANGO_SETTINGS_MODULE = "config.settings.production"
$env:DJANGO_SECURE_SSL_REDIRECT = "false"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost"
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py runserver 127.0.0.1:8001 --noreload    # open http://127.0.0.1:8001
```

```bash
# Linux / macOS
(cd frontend && npm run build)
cd backend
export DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_SECURE_SSL_REDIRECT=false DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
python manage.py collectstatic --noinput
python manage.py check --deploy
python manage.py runserver 127.0.0.1:8001 --noreload
```

`runserver` is only for this local check; the real deployment server and HTTPS setup are part of M11.
Production settings require a real `DJANGO_SECRET_KEY` (50+ random characters) and refuse to start without
one.

## Libraries, services and tools disclosure

- **Libraries**: listed with versions in [docs/architecture.md](docs/architecture.md#1-stack-resolved-versions-m1),
  `backend/requirements.txt` and `frontend/package-lock.json`. Icons: lucide-react (ISC). Urdu font: Noto Nastaliq Urdu (SIL Open Font
  License) via `@fontsource/noto-nastaliq-urdu`, self-hosted.
- **External services / AI providers**: ElevenLabs (Scribe speech-to-text and `eleven_v3` text-to-speech), Groq (`openai/gpt-oss-120b`: interpretation, Urdu job descriptions, quotation agreement check), and optionally Google Gemini API (speech-to-text, interpretation, agreement check) and Azure AI Speech (text-to-speech), used only when keys are configured; M2 phone confirmation is a labelled simulation. CNIC OCR uses the locally installed
  Tesseract OCR engine (Apache-2.0) via its command line, with Pillow (MIT-CMU) for image checks. The identity
  registry is a local, fictional, demo-only simulation. OTP and NADRA providers are not integrated.
- **AI coding tools**: this codebase is being written with AI coding assistance (Claude Code, Anthropic).
- **Earlier prototype**: the earlier Roshan Rozgaar prototype (the project's former name) served only as
  inspiration; no code was copied or adapted from it.
