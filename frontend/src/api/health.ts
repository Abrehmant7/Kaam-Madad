import { apiRequest } from "./client";

export type HealthCheckState = "ok" | "unavailable";

export interface ReadinessResponse {
  status: "ok";
  checks: Record<string, HealthCheckState>;
}

/** GET /api/v1/health/ready/ — 200 when the backend and database are usable, 503 otherwise. */
export function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>("/health/ready/", { signal });
}
