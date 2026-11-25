# Kaam Madad · کام مدد

> **Name change:** this project was previously called *Roshan Rozgaar*. The requirements PDF still uses
> that name. Internal identifiers (database name/user `roshan_rozgaar`, Compose project/container
> `roshan-rozgaar`, the npm package name) intentionally keep the old name so existing setups keep working.

A mobile-first marketplace connecting customers with nearby skilled tradespeople (electricians, plumbers,
AC technicians). Workers must be able to complete the core journey **without understanding English**,
using Urdu text, spoken instructions, recognisable icons and guided choices.

Built for the Capital Youth Expo, Track 5 — Urdu & Regional Tech.

> **Status: Modules M1 (Foundation) and M2 (Accounts, language, catalog) complete.** Workers and customers
> can sign up, log in, confirm their phone through a clearly labelled **demo** flow, switch Urdu/English, and
> see a minimal role home. The trade/service/area catalog is in the database. Worker onboarding, job
> requests, recommendations, chat, quotations and bookings are **not** implemented yet.
> See [docs/progress.md](docs/progress.md).

- Requirements: [docs/requirements.md](docs/requirements.md)
- Architecture and decisions: [docs/architecture.md](docs/architecture.md)
- API contracts: [docs/api.md](docs/api.md)
- Module progress, checks run, limitations: [docs/progress.md](docs/progress.md)

## Stack

Django 6.1 + Django REST Framework · PostgreSQL 18 · React 19 + TypeScript 7 + Vite 8 + Tailwind CSS 4.
Sessions with HttpOnly cookies and CSRF; in production Django serves the API, admin and built frontend from
one origin. Full version list: [docs/architecture.md](docs/architecture.md#1-stack-resolved-versions-m1).

## Prerequisites

- Python **3.12+** (tested 3.14)
- Node.js **22.22+** (tested 24.12) and npm
- **Either** Docker Desktop / Docker Engine with Compose **or** an existing PostgreSQL 14+ server

No speech, OCR, OTP, NADRA or other provider keys are needed (none are integrated yet; see
[Integrations not available yet](#integrations-not-available-yet)).

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

## 5. Using the app (M2)

Local development runs as a **demo deployment** (`APP_DEPLOYMENT_MODE=demo`): every screen shows a demo banner
and new accounts are marked as demo accounts. Use fictional phone numbers.

**Create a worker and a customer**
1. Open http://localhost:5173 → **شروع کریں / Get started**.
2. Choose a language (applies immediately), then **میں کاریگر ہوں / I am a worker** or
   **مجھے کاریگر چاہیے / I need a worker** → continue.
3. Enter a mobile number (any format, e.g. `0300 1234567`) and a password (8+ characters, not only digits,
   not a common password) twice → **Create account**. You are logged in and taken to phone confirmation.
4. Log out (header button) and repeat with another number and the other role.

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
| NADRA / identity verification, CNIC OCR | Not implemented (M4; NADRA only with authorised access) |
| Speech-to-text, interpretation, text-to-speech | Not implemented (M3). The audio control exists but shows nothing without real audio. |
| Recommendations, chat, quotations, bookings, reviews, reports | Not implemented (M6–M10) |

## 6. Checks and tests

```bash
# Backend (from backend/, venv active) — runs against a real PostgreSQL test database
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --settings=config.settings.test

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

## 7. Production-like local run (same origin)

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
- **External services / AI providers**: none yet (M2 phone confirmation is a labelled simulation). Speech, interpretation, OCR, TTS, OTP and identity
  providers arrive in later modules and will be documented with their exact modes.
- **AI coding tools**: this codebase is being written with AI coding assistance (Claude Code, Anthropic).
- **Earlier prototype**: the earlier Roshan Rozgaar prototype (the project's former name) served only as
  inspiration; no code was copied or adapted from it.
