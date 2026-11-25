import { describe, expect, it, vi } from "vitest";

import { errorEnvelope, jsonResponse } from "../test/http";
import { ApiError, apiRequest, ConnectionError, setUnauthorizedHandler } from "./client";

describe("apiRequest", () => {
  it("returns parsed JSON and calls the same-origin /api/v1 path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/health/live/")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/health/live/",
      expect.objectContaining({ method: "GET", credentials: "same-origin" }),
    );
  });

  it("turns the error envelope into an ApiError with code, request id and details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(errorEnvelope("service_not_ready", "req-1", { checks: { database: "unavailable" } }), 503),
      ),
    );

    const error = await apiRequest("/health/ready/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "service_not_ready",
      requestId: "req-1",
      details: { checks: { database: "unavailable" } },
    });
  });

  it("treats a network failure as an unreachable connection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await apiRequest("/health/ready/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ConnectionError);
    expect((error as ConnectionError).reason).toBe("unreachable");
  });

  it("reports offline when the browser says it is offline", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    const error = await apiRequest("/health/ready/").catch((e: unknown) => e);
    expect((error as ConnectionError).reason).toBe("offline");
  });

  it("treats a gateway response without the envelope as unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Bad Gateway", { status: 502, headers: { "Content-Type": "text/plain" } })),
    );
    const error = await apiRequest("/health/ready/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ConnectionError);
    expect(error).toMatchObject({ reason: "unreachable", status: 502 });
  });

  it("times out a request that never answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      ),
    );
    const error = await apiRequest("/health/ready/", { timeoutMs: 20 }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ConnectionError);
    expect((error as ConnectionError).reason).toBe("timeout");
  });

  it("sends the CSRF cookie on mutations and retries once after csrf_failed", async () => {
    document.cookie = "csrftoken=stale-token";
    let posts = 0;
    const calls: Array<{ url: string; token: string | undefined }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit = {}) => {
        const token = (init.headers as Record<string, string>)["X-CSRFToken"];
        calls.push({ url, token });
        if (url.endsWith("/auth/csrf/")) {
          document.cookie = "csrftoken=fresh-token";
          return jsonResponse({ csrf_token: "fresh-token" });
        }
        posts += 1;
        return posts === 1
          ? jsonResponse(errorEnvelope("csrf_failed", "r-csrf"), 403)
          : jsonResponse({ ok: true });
      }),
    );

    await expect(apiRequest("/auth/logout/", { method: "POST" })).resolves.toEqual({ ok: true });
    expect(calls.map((call) => [call.url, call.token])).toEqual([
      ["/api/v1/auth/logout/", "stale-token"],
      ["/api/v1/auth/csrf/", undefined],
      ["/api/v1/auth/logout/", "fresh-token"],
    ]);
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("reports a 401 to the session-expired handler unless told not to", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(errorEnvelope("not_authenticated", "r5"), 401)));
    await expect(apiRequest("/auth/phone-confirmation/")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
    await expect(apiRequest("/auth/me/", { skipUnauthorizedHandler: true })).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
    setUnauthorizedHandler(null);
  });

  it("propagates caller cancellation instead of reporting a failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      ),
    );
    const controller = new AbortController();
    const pending = apiRequest("/health/ready/", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort();
    const error = await pending;
    expect(error).not.toBeInstanceOf(ConnectionError);
    expect((error as DOMException).name).toBe("AbortError");
  });
});
