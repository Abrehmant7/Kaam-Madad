import { describe, expect, it, vi } from "vitest";

import { errorEnvelope, jsonResponse } from "../test/http";
import { ApiError, apiRequest, ConnectionError } from "./client";

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
