# Kaam Madad — Module Progress

Requirements: [requirements.md](requirements.md) · Architecture: [architecture.md](architecture.md)

> **25 Nov 2026 — brand rename (M1 follow-up):** public name changed from *Roshan Rozgaar* to
> **Kaam Madad / کام مدد** in UI strings, page title/metadata, admin header, README and docs. Internal
> identifiers (database `roshan_rozgaar`, Compose project `roshan-rozgaar`, npm package name) are unchanged
> on purpose; see [architecture.md](architecture.md) "Naming". Frontend typecheck, tests and build re-run
> after the change.

| Module | Status |
|---|---|
| M1 Foundation | ✅ Complete (24 Nov 2026) |
| M2 Accounts, language, catalog | ⬜ Next |
| M3 Audio and AI adapters | ⬜ Not started |
| M4 Worker onboarding | ⬜ Not started |
| M5 Customer and job requests | ⬜ Not started |
| M6 Recommendations and invitations | ⬜ Not started |
| M7 Communication and agreements | ⬜ Not started |
| M8 Booking and arrival | ⬜ Not started |
| M9 Completion and feedback | ⬜ Not started |
| M10 Reporting and moderation | ⬜ Not started |
| M11 Integration and delivery | ⬜ Not started |

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
