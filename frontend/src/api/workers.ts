import { apiRequest } from "./client";

export type OnboardingStep = "work" | "areas";

export interface WorkerProfileData {
  trade: string | null;
  services_offered: string[];
  primary_specialities: string[];
  services_not_offered: string[];
  city: string | null;
  service_areas: string[];
  accepting_requests: boolean;
  updated_at: string;
}

export type IdentityStatus =
  | "not_started"
  | "in_progress"
  | "no_match"
  | "demo_approved"
  | "provider_verified"
  | "manually_reviewed"
  | "rejected"
  | "expired"
  | "suspended";

export interface IdentitySummary {
  status: IdentityStatus;
  case_id: string | null;
  method: string | null;
  masked_cnic: string | null;
  simulated: boolean;
  /** Whether this status is accepted for taking jobs in this deployment. */
  counts_here: boolean;
  decided_at: string | null;
  updated_at: string | null;
}

export interface Eligibility {
  can_take_jobs: boolean;
  receives_requests: boolean;
  reasons: string[];
}

export interface ProviderStatus {
  provider: string;
  available: boolean;
  simulated: boolean;
}

export interface WorkerDashboard {
  profile: WorkerProfileData;
  onboarding: {
    complete: boolean;
    next_step: OnboardingStep | null;
    steps: Record<OnboardingStep, { complete: boolean; issues: string[] }>;
  };
  identity: IdentitySummary;
  eligibility: Eligibility;
  identity_provider: ProviderStatus;
}

export interface WorkPayload {
  trade: string;
  services_offered: string[];
  primary_specialities: string[];
  services_not_offered: string[];
}

export interface AreasPayload {
  city: string;
  service_areas: string[];
}

export interface IdentityCase extends IdentitySummary {
  id: string;
  consent: { given_at: string; version: string };
  scan: { count: number; scanned_at: string | null; width: number | null; height: number | null };
  ocr: {
    status: "not_run" | "read" | "partial" | "unreadable" | "failed";
    provider: string | null;
    engine: string | null;
    rotation: number;
    /** Setup or engine reason when status is "failed" (e.g. "tesseract_not_found"). */
    failure: string | null;
    simulated: boolean;
    /** The ORIGINAL scan result, for review; cleared once the attempt is approved. */
    name: string | null;
    cnic_number: string | null;
  };
  review: { submitted_at: string | null; name_corrected: boolean; number_corrected: boolean };
  registry: {
    outcome: "not_checked" | "match" | "name_mismatch" | "no_record";
    provider: string | null;
    simulated: boolean;
    reference: string | null;
    checked_at: string | null;
    attempts: number;
    /** Fictional, labelled "Demo address"; never a service area. */
    demo_address: string | null;
  };
}

export const fetchWorker = (signal?: AbortSignal) => apiRequest<WorkerDashboard>("/workers/me/", { signal });

export const saveWork = (payload: WorkPayload) =>
  apiRequest<WorkerDashboard>("/workers/me/work/", { method: "PUT", body: payload });

export const saveAreas = (payload: AreasPayload) =>
  apiRequest<WorkerDashboard>("/workers/me/areas/", { method: "PUT", body: payload });

export const setAcceptingRequests = (accepting_requests: boolean) =>
  apiRequest<WorkerDashboard>("/workers/me/preferences/", { method: "PATCH", body: { accepting_requests } });

export const fetchIdentityCase = (signal?: AbortSignal) =>
  apiRequest<{ case: IdentityCase | null; provider: ProviderStatus }>("/identity/cases/", { signal });

export const startIdentityCase = () =>
  apiRequest<{ case: IdentityCase; provider: ProviderStatus }>("/identity/cases/", { method: "POST", body: { consent: true } });

/** Photo of the card front → OCR on the server (the image is not stored). */
export function scanCard(caseId: string, file: Blob, name = "card") {
  const form = new FormData();
  form.append("image", file, name);
  return apiRequest<{ case: IdentityCase }>(`/identity/cases/${caseId}/scan/`, { method: "POST", body: form, timeoutMs: 60000 });
}

export const submitDetails = (caseId: string, name: string, cnic_number: string) =>
  apiRequest<{ case: IdentityCase; eligibility: Eligibility }>(`/identity/cases/${caseId}/submit/`, {
    method: "POST",
    body: { name, cnic_number },
  });
