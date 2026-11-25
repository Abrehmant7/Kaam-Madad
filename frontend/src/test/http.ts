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
