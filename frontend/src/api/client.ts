/**
 * Minimal JSON client for the Django API (same origin, session cookies).
 *
 * Failures are split into two kinds the UI can explain differently:
 * - ApiError: the backend answered with the shared error envelope
 *   `{ "error": { code, message, request_id, fields?, details? } }`.
 *   UI text is chosen from `code`; `message` is only an English fallback.
 * - ConnectionError: no usable answer from the backend (offline, timeout,
 *   network failure, or a gateway/proxy response without the envelope).
 */

export const API_BASE = "/api/v1";
export const DEFAULT_TIMEOUT_MS = 10_000;

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

export interface RequestOptions {
  method?: "GET";
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Perform an API request and return the parsed JSON body.
 * Mutating methods (with CSRF headers) are added in M2 with authentication.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });

  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, {
        method,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
    } catch (error) {
      if (signal?.aborted) throw error; // Cancelled by the caller: not a failure to report.
      if (timedOut) throw new ConnectionError("timeout");
      throw new ConnectionError(isOffline() ? "offline" : "unreachable");
    }

    const headerRequestId = response.headers.get("X-Request-ID");
    const body = await readJson(response);
    if (signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
    if (timedOut) throw new ConnectionError("timeout");

    if (response.ok) return body as T;
    if (isErrorEnvelope(body)) throw new ApiError(response.status, body.error, headerRequestId);
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
