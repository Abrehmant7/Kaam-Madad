# Kaam Madad — Architecture and Implementation Decisions

Requirements: [requirements.md](requirements.md) · Progress: [progress.md](progress.md)

**Naming.** Public brand: **Kaam Madad** (English) / **کام مدد** (Urdu), shown through the `app.name`
translation key, page metadata and the admin header. The project was formerly *Roshan Rozgaar*; internal
identifiers keep that name to avoid coordinated migrations: database name/user `roshan_rozgaar`, Compose
project `roshan-rozgaar` (container `roshan-rozgaar-db-1` and its data volume), npm package
`roshan-rozgaar-frontend`. Django apps (`apps.core`, `apps.accounts`), migrations, env keys and API routes
never contained the brand. New user-facing text must use `t("app.name")`, not a literal name.

This document records how the system is built and why. It describes what exists **now** (after M1)
and marks decisions intentionally left to later modules.

## 1. Stack (resolved versions, M1)

| Layer | Choice | Version |
|---|---|---|
| Backend runtime | Python | 3.14.0 tested (Django 6.1 requires ≥ 3.12) |
| Web framework | Django | 6.1.3 |
| API | Django REST Framework | 3.18.3 (declares Django 6.1 support) |
| Database | PostgreSQL | 18.7 (Docker image `postgres:18-alpine`) |
| DB driver | psycopg (binary) | 3.3.9 |
| Static/SPA serving | WhiteNoise | 6.12.0 |
| Local env loading | python-dotenv | 1.2.4 |
| Frontend runtime | Node.js | 24.12 tested (React Router 8 requires ≥ 22.22) |
| UI | React / React DOM | 19.3.1 |
| Routing | React Router | 8.5.2 |
| Build | Vite / @vitejs/plugin-react | 8.3.8 / 6.3.0 |
| Language | TypeScript | 7.0.2 |
| Styling | Tailwind CSS (+ @tailwindcss/vite) | 4.3.5 |
| Urdu font | @fontsource/noto-nastaliq-urdu (bundled, self-hosted) | 5.3.0 |
| Frontend tests | Vitest, jsdom, Testing Library (react, dom, jest-dom, user-event) | 5.1.1, 31.0.1, 16.3.3 / 10.4.2 / 8.0.0 / 14.6.13 |

Exact backend pins live in `backend/requirements.txt` (direct ranges in `backend/requirements.in`); exact
frontend versions live in `frontend/package-lock.json`.

Not used, by design (requirements §2): microservices, Redis, Celery, vector databases, agent frameworks,
WebSockets (polling is the MVP update mechanism).

## 2. Repository layout

```
.
├── .env.example            Backend + Docker Compose configuration template (copy to .env)
├── docker-compose.yml      Local PostgreSQL only (host port 5434 by default)
├── docs/                   requirements.md, architecture.md, progress.md
├── backend/
│   ├── manage.py           Defaults to config.settings.development
│   ├── requirements.in/.txt
│   ├── config/
│   │   ├── env.py          Typed env-var helpers (no values echoed in errors)
│   │   ├── settings/       base.py, development.py, production.py, test.py
│   │   ├── urls.py         /api/v1/, /admin/, SPA catch-all, API-aware error handlers
│   │   └── wsgi.py/asgi.py Default to production settings
│   └── apps/
│       ├── core/           Request IDs, logging filter, error envelope, exception handler,
│       │                   health endpoints, SPA view, static cache policy
│       └── accounts/       Custom User model, phone normalisation, manager, admin
└── frontend/
    ├── index.html          lang="ur" dir="rtl" by default
    ├── vite.config.ts      Dev proxy for /api, /admin, /static → Django
    ├── vitest.config.ts
    └── src/
        ├── api/            client.ts (envelope parsing, timeouts), health.ts
        ├── i18n/           Urdu/English resources, provider, types
        ├── components/     AppShell layout, inline icons, <Ltr> bidi isolation
        ├── features/health ServerStatusCard + useServerStatus
        ├── pages/          Landing, NotFound, RouteError
        └── routes.tsx      Route table (feature modules add routes here)
```

The pre-existing empty `index.py` in the repository root is a user file and is left untouched.
No code from the earlier Roshan Rozgaar prototype (the project's former name) was used.

## 3. Runtime topology

**Development** — two processes, one browser origin:

```
Browser ──► http://localhost:5173 (Vite dev server)
              ├── /src, /@vite, assets ──► served by Vite (hot reload)
              └── /api, /admin, /static ──► proxied to Django http://127.0.0.1:8000
Django ──► PostgreSQL 127.0.0.1:5434 (Docker Compose)
```

The proxy keeps the browser's `Host` header (`changeOrigin: false`), so Django sees the same origin as the
page and session/CSRF cookies behave as in production.

**Production** — one Django deployment serves everything from one origin:

| Path | Served by | Caching |
|---|---|---|
| `/api/v1/...` | DRF views | API responses as set per view (health: `no-store`) |
| `/admin/...` | Django Admin | — |
| `/static/...` | WhiteNoise, from `collectstatic` (manifest-hashed) | immutable, 10 years |
| `/assets/...`, `/favicon.svg` | WhiteNoise, from `frontend/dist` (`WHITENOISE_ROOT`) | hashed files immutable; others revalidated |
| any other path | `spa_index` view → `frontend/dist/index.html` | `no-cache` so new deploys load immediately |

Unknown `/api/...` paths always return the JSON 404 envelope and never fall through to the SPA.
The WSGI server choice (e.g. gunicorn on Linux) and HTTPS termination are decided in M11.

## 4. Backend decisions

### Settings
- `base.py` holds everything shared; `development.py` (DEBUG, insecure fallback key, local hosts),
  `production.py` (fail-fast checks, HTTPS, secure cookies, HSTS, manifest static storage),
  `test.py` (development + fast MD5 hasher for tests only).
- Production **refuses to start** without a ≥ 50-character non-`django-insecure` `DJANGO_SECRET_KEY` or
  without `DJANGO_ALLOWED_HOSTS` (covered by subprocess tests).
- The repository-root `.env` is loaded with `override=False`: real environment variables always win.
- `TIME_ZONE = "Asia/Karachi"`, `USE_TZ = True`: timestamps stored in UTC, displayed in Karachi time.
- `POSTGRES_HOST` defaults to **`127.0.0.1`, not `localhost`**. Measured on Windows + Docker Desktop:
  with `localhost`, libpq tries IPv6 `::1` first, where the published port hangs until
  `connect_timeout` — adding ~5 s to *every* new connection and ~10 s to a failed readiness check.
  With `127.0.0.1`: connect ≈ 0.05 s; readiness failure ≈ 3.3 s (timeout 3 s).

### Custom user model (`apps/accounts`)
Defined before the first migration (`accounts.0001_initial`).

| Field | Notes |
|---|---|
| `id` | UUID4 primary key — opaque external identifier |
| `phone_number` | Login identity (`USERNAME_FIELD`), unique, stored as E.164 `+923XXXXXXXXX` |
| `role` | `worker` / `customer`; empty for staff-only accounts. **Grants no staff permission.** |
| `preferred_language` | `ur` (default) / `en` |
| `is_active` | Standard Django active flag |
| `is_demo` | Fictional/test account marker for labelling and separation (NFR-04) |
| `is_staff`, `is_superuser`, groups, permissions | Standard Django — the only source of staff authority |
| `date_joined`, `updated_at`, `last_login`, `password` | Standard; passwords hashed by Django (PBKDF2 default) |

- **Phone normalisation** (`apps/accounts/phone.py`) accepts what people type — `0300 1234567`,
  `+92 300 1234567`, `00923…`, `3001234567`, Urdu/Arabic-Indic digits, invisible bidi marks — and accepts
  **mobile numbers only** (the future OTP target). Applied in the manager, `clean()`, `save()`, admin forms,
  admin search, and `get_by_natural_key` (so login works with any format).
- **Database constraints** enforce the invariants even if Python validation is bypassed: phone regex
  `^\+923[0-9]{9}$`, valid role set, valid language set, unique phone. Verified with `\d accounts_user`.
- **Masking**: `str(user)` and admin lists show `+92 3** ***4567`; the full number appears only on a user's
  own admin change page.
- CNIC is never a username or login field.
- Planned additions (later modules, via migrations): restricted state and phone-confirmation method
  (M2/M10). Role immutability after signup is enforced in the M2 signup/profile API.

### API conventions (`apps/core`)
- Prefix `/api/v1/`. JSON only (JSON renderer/parser).
- **Default deny**: `IsAuthenticated` + `SessionAuthentication` globally; public endpoints opt in.
- **Error envelope** (requirements §10), produced by `api_exception_handler` and the API-aware Django
  `handler400/403/404/500`:

  ```json
  {"error": {"code": "validation_error", "message": "Some submitted values are invalid.",
             "request_id": "…", "fields": {"items.1.amount": [{"code": "invalid", "message": "…"}]},
             "details": {"…": "non-sensitive context, e.g. current state for a 409"}}}
  ```
  `code` is stable and drives client translations; `message` is an English fallback; `fields` appears
  only for validation errors (nested errors flattened to dotted paths); `details` is optional.
  Exception text, SQL, stack traces and credentials never appear in responses.
- Application errors raise `ApiError(message, code, details=…, status_code=…)`.
- **Request IDs**: a server-generated UUID per request, in `X-Request-ID`, in every error body, and in every
  log line (client-supplied IDs are ignored to prevent spoofing/log injection).
- **Health**:
  - `GET /api/v1/health/live/` → `200 {"status":"ok"}`. No database, session or auth access (asserted with
    zero queries).
  - `GET /api/v1/health/ready/` → `200 {"status":"ok","checks":{"database":"ok"}}`, or
    `503` envelope `service_not_ready` with `details.checks.database = "unavailable"`. The failure is
    logged by exception class name only. Both are `Cache-Control: no-store` and exempt from the HTTPS
    redirect (platform probes).

### Admin
`UserAdmin` with phone-aware creation/change forms, masked list display, filters (role, active, staff,
superuser, demo, language), and search that normalises a full phone number in any format. Header:
"Kaam Madad staff administration". Marketplace users without `is_staff` are redirected to the admin
login (tested).

### Media
`PRIVATE_MEDIA_ROOT` (`backend/private_media/`, git-ignored) is configured as `MEDIA_ROOT` but **no URL
serves it**. M3 adds authorised download views (MEDIA-01).

## 5. Frontend decisions

- **Mobile-first shell**: single column, `max-w-lg`, 16 px gutters; verified with Chrome DevTools-protocol
  device emulation at **360 px**: no horizontal overflow in Urdu or English.
- **i18n structure** (`src/i18n`): Urdu resource is the source of keys; English is type-checked for
  parity (`Record<TranslationKey, string>`) and tested at runtime. `I18nProvider` sets
  `<html lang dir>`, defaults to Urdu/RTL, persists the choice in `localStorage` (guarded). The visible
  language switch and server-side preference sync are **M2**.
- **RTL/Urdu rendering**: Noto Nastaliq Urdu (Arabic-script subset, 400/700, ~160 KB woff2 each) is bundled
  and self-hosted; Latin text uses the system font. Urdu gets larger text and taller line heights by
  overriding Tailwind's `--text-*--line-height` variables under `html:lang(ur)`. Layout uses logical
  (start/end) properties. `<Ltr>` (`<bdi dir="ltr">`) isolates numbers, codes and IDs inside Urdu text.
- **Accessibility baseline**: skip link, visible focus ring, `role="status"` + `aria-live` for async
  state, icon + text on every action, 44 px minimum touch targets (retry button measured at 52 px).
- **API client** (`src/api/client.ts`): same-origin `fetch` with credentials, 10 s timeout, caller
  cancellation. Errors are `ApiError` (envelope from Django: code, requestId, fields, details) or
  `ConnectionError` (`offline` / `timeout` / `unreachable`, including non-envelope 5xx from a
  proxy/gateway, e.g. Vite's 502 when Django is down). CSRF header handling for mutations arrives with
  authentication in M2.
- **Landing screen**: identifies the product, states plainly that registration/requests/bookings are not
  available yet, and shows live readiness: checking → ready / database unavailable (with reference
  number) / offline / timeout / unreachable / unexpected, with a retry action. No fake lists or simulated
  integrations.

## 6. Security posture after M1

- Secrets only in environment variables; `.env`, `.env.*` (except `.env.example`), private media,
  virtualenvs, `node_modules`, build output and `staticfiles` are git-ignored.
- Production: HTTPS redirect, `Secure` + `HttpOnly` session cookie, `Secure` CSRF cookie, `SameSite=Lax`,
  HSTS (3600 s default, configurable), nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`.
- `check --deploy` with production settings reports only HSTS include-subdomains/preload (domain decisions
  for M11) and, in the local HTTP smoke test only, the deliberately disabled SSL redirect.
- Logs carry request IDs and never driver error messages from readiness checks.

## 7. Decisions deferred (and where)

| Topic | Module |
|---|---|
| Signup/login/logout/me/CSRF bootstrap endpoints, role immutability, rate limits, demo-labelled phone adapter | M2 |
| Visible Urdu/English switch, preference sync with the account, reusable audio/icon controls | M2 |
| Deployment mode (production vs demo) configuration + startup check rejecting simulated providers (NFR-04) | M2/M3 (when simulated providers exist) |
| Password policy suited to low-literacy users (Django defaults apply for now) | M2 |
| Provider adapters, private media upload/download | M3 |
| Content-Security-Policy (needs browser verification of admin + SPA), WSGI server, HTTPS deployment, HSTS subdomains/preload | M11 |
