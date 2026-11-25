// Helpers for building fetch responses in tests. They only shape HTTP
// responses; the code under test still parses them exactly as in the browser.

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function errorEnvelope(code: string, requestId: string, details?: Record<string, unknown>) {
  return { error: { code, message: `${code} message`, request_id: requestId, ...(details ? { details } : {}) } };
}
