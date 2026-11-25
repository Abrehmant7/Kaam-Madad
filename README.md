# Kaam Madad · کام مدد

> **Name change:** this project was previously called *Roshan Rozgaar*. The requirements PDF still uses
> that name. Internal identifiers (database name/user `roshan_rozgaar`, Compose project/container
> `roshan-rozgaar`, the npm package name) intentionally keep the old name so existing setups keep working.

A mobile-first marketplace connecting customers with nearby skilled tradespeople (electricians, plumbers,
AC technicians). Workers must be able to complete the core journey **without understanding English**,
using Urdu text, spoken instructions, recognisable icons and guided choices.

Built for the Capital Youth Expo, Track 5 — Urdu & Regional Tech.

> **Status: Module M1 (Foundation) complete.** The app currently provides the project skeleton, the
> custom user model, health checks, and an Urdu landing page showing live server status. Registration,
> job requests and bookings are **not** implemented yet. See [docs/progress.md](docs/progress.md).

- Requirements: [docs/requirements.md](docs/requirements.md)
- Architecture and decisions: [docs/architecture.md](docs/architecture.md)
- Module progress, checks run, limitations: [docs/progress.md](docs/progress.md)

## Stack

Django 6.1 + Django REST Framework · PostgreSQL 18 · React 19 + TypeScript 7 + Vite 8 + Tailwind CSS 4.
Sessions with HttpOnly cookies and CSRF; in production Django serves the API, admin and built frontend from
one origin. Full version list: [docs/architecture.md](docs/architecture.md#1-stack-resolved-versions-m1).

## Prerequisites

- Python **3.12+** (tested 3.14)
- Node.js **22.22+** (tested 24.12) and npm
- **Either** Docker Desktop / Docker Engine with Compose **or** an existing PostgreSQL 14+ server

No speech, OCR, OTP, NADRA or other provider keys are needed for M1.

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
python manage.py migrate
python manage.py createsuperuser      # phone number, e.g. 03001234567 (no spaces), then a password
python manage.py runserver 127.0.0.1:8000
```

```bash
# Linux / macOS
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # phone number, e.g. 03001234567 (no spaces), then a password
python manage.py runserver 127.0.0.1:8000
```

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

## 5. Checks and tests

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

## 6. Production-like local run (same origin)

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
  `backend/requirements.txt` and `frontend/package-lock.json`. Urdu font: Noto Nastaliq Urdu (SIL Open Font
  License) via `@fontsource/noto-nastaliq-urdu`, self-hosted.
- **External services / AI providers**: none in M1. Speech, interpretation, OCR, TTS, OTP and identity
  providers arrive in later modules and will be documented with their exact modes.
- **AI coding tools**: this codebase is being written with AI coding assistance (Claude Code, Anthropic).
- **Earlier prototype**: the earlier Roshan Rozgaar prototype (the project's former name) served only as
  inspiration; no code was copied or adapted from it.
