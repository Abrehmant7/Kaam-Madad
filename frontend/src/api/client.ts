/**
 * Minimal JSON client for the Django API (same origin, session cookies).
 *
 * Failures are split into two kinds the UI can explain differently:
 * - ApiError: the backend answered with the shared error envelope
 *   `{ "error": { code, message, request_id, fields?, details? } }`.
 *   UI text is chosen from `code`; `message` is only an English fallback.
 *   401 `not_authenticated` = no valid session; 403 = not allowed.
 * - ConnectionError: no usable answer from the backend (offline, timeout,
 *   network failure, or a gateway/proxy response without the envelope).
 *
 * Mutations send the CSRF token from the `csrftoken` cookie in `X-CSRFToken`.
 * If the server reports `csrf_failed` (e.g. the token rotated at login), the
 * client fetches a fresh token and retries the request once.
 */

export const API_BASE = "/api/v1";
export const DEFAULT_TIMEOUT_MS = 10_000;
const CSRF_COOKIE = "csrftoken";

export interface FieldError {
  code: string;
  message: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string | null;
  fields?: Record<string, FieldError[]>;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly fields: Record<string, FieldError[]>;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody, headerRequestId: string | null = null) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.requestId = body.request_id ?? headerRequestId;
    this.fields = body.fields ?? {};
    this.details = body.details ?? {};
  }
}

export type ConnectionFailureReason = "offline" | "timeout" | "unreachable";

export class ConnectionError extends Error {
  readonly reason: ConnectionFailureReason;
  /** HTTP status when a gateway/proxy answered instead of the backend. */
  readonly status: number | null;
  readonly requestId: string | null;

  constructor(reason: ConnectionFailureReason, status: number | null = null, requestId: string | null = null) {
    super(`Connection failure: ${reason}`);
    this.name = "ConnectionError";
    this.reason = reason;
    this.status = status;
    this.requestId = requestId;
  }
}

export function isNotAuthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as ApiErrorBody).code === "string" &&
    typeof (error as ApiErrorBody).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) return undefined;
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

function isOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (rawKey === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

// Fallback when the cookie cannot be read (the server also returns the token in JSON).
let csrfTokenFromBody: string | null = null;

function csrfToken(): string | null {
  return readCookie(CSRF_COOKIE) ?? csrfTokenFromBody;
}

// Called when an authenticated-looking request comes back 401 (session expired).
let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Do not report a 401 as "session expired" (e.g. login itself). */
  skipUnauthorizedHandler?: boolean;
}

async function send<T>(path: string, options: RequestOptions): Promise<T> {
  const { method = "GET", body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });

  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    const token = csrfToken();
    if (token) headers["X-CSRFToken"] = token;
  }
  if (body !== undefined) headers["Content-Type"] = "application/json";

  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method,
        credentials: "same-origin",
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (signal?.aborted) throw error; // Cancelled by the caller: not a failure to report.
      if (timedOut) throw new ConnectionError("timeout");
      throw new ConnectionError(isOffline() ? "offline" : "unreachable");
    }

    const headerRequestId = response.headers.get("X-Request-ID");
    const parsed = await readJson(response);
    if (signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
    if (timedOut) throw new ConnectionError("timeout");

    if (response.ok) return parsed as T;
    if (isErrorEnvelope(parsed)) throw new ApiError(response.status, parsed.error, headerRequestId);
    if (response.status >= 500) {
      // A proxy or gateway answered because the backend could not.
      throw new ConnectionError("unreachable", response.status, headerRequestId);
    }
    throw new ApiError(
      response.status,
      { code: "unexpected_response", message: "Unexpected response from the server.", request_id: null },
      headerRequestId,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

/** Fetch (and remember) a CSRF token; also sets the csrftoken cookie. */
export async function refreshCsrfToken(signal?: AbortSignal): Promise<string> {
  const result = await send<{ csrf_token: string }>("/auth/csrf/", { signal });
  csrfTokenFromBody = result.csrf_token;
  return result.csrf_token;
}

/** Perform an API request and return the parsed JSON body (undefined for 204). */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  try {
    return await send<T>(path, { ...options, method });
  } catch (error) {
    if (error instanceof ApiError && error.code === "csrf_failed" && method !== "GET") {
      await refreshCsrfToken(options.signal);
      return await send<T>(path, { ...options, method });
    }
    if (isNotAuthenticated(error) && !options.skipUnauthorizedHandler) {
      unauthorizedHandler?.();
    }
    throw error;
  }
}
