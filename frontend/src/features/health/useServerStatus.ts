import { useCallback, useEffect, useState } from "react";

import { ApiError, ConnectionError, type ConnectionFailureReason } from "../../api/client";
import { fetchReadiness } from "../../api/health";

export type ServerStatus =
  | { kind: "checking" }
  | { kind: "ready" }
  | { kind: "not_ready"; requestId: string | null }
  | { kind: "connection_error"; reason: ConnectionFailureReason }
  | { kind: "unexpected"; requestId: string | null };

export function classifyReadinessError(error: unknown): ServerStatus {
  if (error instanceof ApiError) {
    return error.code === "service_not_ready"
      ? { kind: "not_ready", requestId: error.requestId }
      : { kind: "unexpected", requestId: error.requestId };
  }
  if (error instanceof ConnectionError) {
    return { kind: "connection_error", reason: error.reason };
  }
  return { kind: "unexpected", requestId: null };
}

/** Checks backend readiness once on mount and again whenever `retry` is called. */
export function useServerStatus() {
  const [status, setStatus] = useState<ServerStatus>({ kind: "checking" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchReadiness(controller.signal)
      .then((body) => {
        if (controller.signal.aborted) return;
        setStatus(body?.status === "ok" ? { kind: "ready" } : { kind: "unexpected", requestId: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setStatus(classifyReadinessError(error));
      });
    return () => controller.abort();
  }, [attempt]);

  const retry = useCallback(() => {
    setStatus({ kind: "checking" });
    setAttempt((value) => value + 1);
  }, []);

  return { status, retry };
}
