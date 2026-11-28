import { vi } from "vitest";

// Helpers for building fetch responses in tests. They only shape HTTP
// responses; the code under test still parses them exactly as in the browser.

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function errorEnvelope(code: string, requestId: string, details?: Record<string, unknown>, fields?: Record<string, unknown>) {
  return {
    error: {
      code,
      message: `${code} message`,
      request_id: requestId,
      ...(details ? { details } : {}),
      ...(fields ? { fields } : {}),
    },
  };
}

type Handler = Response | ((init: RequestInit) => Response | Promise<Response>);

export interface RecordedCall {
  method: string;
  path: string;
  headers: Record<string, string>;
  body: unknown;
}

/**
 * Stub `fetch` with handlers keyed by "METHOD /api/v1/path/". Unmatched calls
 * fail loudly. Returns the list of calls for assertions.
 */
export function mockApi(handlers: Record<string, Handler>): RecordedCall[] {
  const calls: RecordedCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method ?? "GET").toUpperCase();
      const path = url.split("?")[0] ?? url;
      const headers = (init.headers ?? {}) as Record<string, string>;
      const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
      calls.push({ method, path, headers, body });
      const handler = handlers[`${method} ${path}`];
      if (!handler) throw new Error(`Unexpected request: ${method} ${url}`);
      const response = typeof handler === "function" ? await handler(init) : handler;
      return response.clone();
    }),
  );
  return calls;
}

export const DEMO_CONFIG = {
  deployment_mode: "demo",
  phone_verification: { provider: "demo", available: true, simulated: true },
  languages: ["ur", "en"],
  default_language: "ur",
};

export function makeUser(overrides: Record<string, unknown> = {}) {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    phone_number_masked: "+92 3** ***4567",
    role: "worker",
    preferred_language: "ur",
    is_demo: true,
    is_staff: false,
    restricted: false,
    phone_confirmation: { status: "unconfirmed", method: null, confirmed_at: null },
    date_joined: "2026-11-25T10:00:00+00:00",
    ...overrides,
  };
}

/** Standard start-up endpoints for an anonymous or signed-in visitor. */
export function bootHandlers(user: Record<string, unknown> | null = null): Record<string, Handler> {
  return {
    "GET /api/v1/auth/csrf/": jsonResponse({ csrf_token: "test-csrf-token" }),
    "GET /api/v1/config/": jsonResponse(DEMO_CONFIG),
    "GET /api/v1/auth/me/": jsonResponse({ authenticated: Boolean(user), user }),
  };
}

const labels = (en: string, ur: string) => ({ en, ur });
const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

export const TRADES = [
  { code: "electrician", labels: labels("Electrician", "الیکٹریشن"), icon: "zap", sort_order: 10, service_count: 3 },
  { code: "plumber", labels: labels("Plumber", "پلمبر"), icon: "wrench", sort_order: 20, service_count: 1 },
];
export const SERVICES = [
  { code: "elec_fan_install", trade: "electrician", labels: labels("Ceiling fan installation", "چھت کے پنکھے کی تنصیب"), icon: "fan", sort_order: 1 },
  { code: "elec_wiring_repair", trade: "electrician", labels: labels("Wiring repair", "وائرنگ کی مرمت"), icon: "cable", sort_order: 2 },
  { code: "elec_ups_inverter", trade: "electrician", labels: labels("UPS / inverter installation", "یو پی ایس"), icon: "battery", sort_order: 3 },
  { code: "plmb_leak_repair", trade: "plumber", labels: labels("Leak repair", "لیکیج کی مرمت"), icon: "droplet", sort_order: 1 },
];
const ISB = { code: "islamabad", labels: labels("Islamabad", "اسلام آباد"), sort_order: 10 };
const RWP = { code: "rawalpindi", labels: labels("Rawalpindi", "راولپنڈی"), sort_order: 20 };
export const AREAS = [
  { code: "isb-g-9", city: ISB, labels: labels("G-9", "جی-9"), kind: "sector", centre: null, sort_order: 1 },
  { code: "isb-g-10", city: ISB, labels: labels("G-10", "جی-10"), kind: "sector", centre: null, sort_order: 2 },
  { code: "rwp-saddar", city: RWP, labels: labels("Saddar", "صدر"), kind: "locality", centre: null, sort_order: 1 },
];
export const QUESTIONS = {
  trade: TRADES[0],
  questions: [
    { code: "services_offered", prompt: labels("", ""), help: labels("", ""), selection: { multiple: true, min: 1, max: null, choices_from: "trade_services" } },
    { code: "primary_specialities", prompt: labels("", ""), help: labels("", ""), selection: { multiple: false, min: 1, max: 1, choices_from: "services_offered" } },
    { code: "services_not_offered", prompt: labels("", ""), help: labels("", ""), selection: { multiple: true, min: 0, max: null, choices_from: "trade_services" } },
  ],
  choices: SERVICES.filter((service) => service.trade === "electrician"),
  rules: [],
};

type Dashboard = Record<string, unknown>;

/** A worker dashboard payload; ``step`` picks where onboarding stands. */
export function makeDashboard(step: "work" | "areas" | null = null, overrides: Dashboard = {}): Dashboard {
  const workDone = step !== "work";
  const complete = step === null;
  return {
    profile: {
      trade: workDone ? "electrician" : null,
      services_offered: workDone ? ["elec_fan_install", "elec_wiring_repair"] : [],
      primary_specialities: workDone ? ["elec_fan_install"] : [],
      services_not_offered: [],
      city: complete ? "islamabad" : null,
      service_areas: complete ? ["isb-g-9"] : [],
      accepting_requests: true,
      updated_at: "2026-11-27T10:00:00+00:00",
    },
    onboarding: {
      complete,
      next_step: step,
      steps: { work: { complete: workDone, issues: workDone ? [] : ["required"] }, areas: { complete, issues: complete ? [] : ["required"] } },
    },
    identity: { status: "not_started", case_id: null, method: null, masked_cnic: null, simulated: false, counts_here: false, decided_at: null, updated_at: null },
    eligibility: { can_take_jobs: false, receives_requests: false, reasons: complete ? ["identity_not_started"] : ["profile_incomplete", "identity_not_started"] },
    identity_provider: { provider: "demo_registry", available: true, simulated: true },
    ...overrides,
  };
}

/** Worker API + catalog handlers for the worker screens. */
export function workerHandlers(dashboard: Dashboard = makeDashboard()): Record<string, Handler> {
  return {
    "GET /api/v1/workers/me/": jsonResponse(dashboard),
    "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
    "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
    "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
    "GET /api/v1/catalog/trades/electrician/speciality-questions/": jsonResponse(QUESTIONS),
    "GET /api/v1/invitations/": jsonResponse(page([])),
    "GET /api/v1/workers/me/stats/": jsonResponse(STATS_EMPTY),
  };
}

/** A new worker's Performance totals: no reviews, nothing completed. */
export const STATS_EMPTY = {
  invitations_received: 0, completed_jobs: 0, review_count: 0, average_rating: null,
  rating_distribution: [5, 4, 3, 2, 1].map((stars) => ({ stars, count: 0 })),
};
