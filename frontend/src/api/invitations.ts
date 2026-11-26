import type { Page } from "./catalog";
import { apiRequest } from "./client";
import type { JobRequest } from "./jobs";

export type InvitationStatus = "active" | "declined" | "withdrawn";
export type DeclineReason = "not_available" | "too_far" | "not_my_work" | "other";

/** What a worker may see about a request (no address, access notes, photos, recordings or customer identity). */
export interface SharedSummary {
  description: string;
  trade: string;
  services: string[];
  services_excluded: string[];
  city: string;
  area: string;
  window_start: string;
  window_end: string;
  budget_preference_pkr: string | null;
  has_photos: boolean;
}

export type MatchReason =
  | { code: "speciality"; services: string[] }
  | { code: "offers"; services: string[] }
  | { code: "serves_area"; area: string };

export interface WorkerCard {
  worker_id: string;
  display_label: string | null;
  trade: string;
  services_matched: string[];
  specialities_matched: string[];
  serves_selected_area: boolean;
  verification: { status: string; simulated: boolean };
  is_new: boolean;
  reasons: MatchReason[];
  previous_invitation: InvitationStatus | null;
}

export interface CustomerInvitation {
  id: string;
  status: InvitationStatus;
  worker: { worker_id: string; display_label: string | null; trade: string | null };
  created_at: string;
  seen_at: string | null;
  closed_at: string | null;
  decline_reason: DeclineReason | null;
  created?: boolean;
}

export interface Recommendations {
  request: { trade: string; services: string[]; city: string; area: string; window_start: string; window_end: string };
  shared_preview: SharedSummary;
  privacy_warnings: ("phone_number" | "address")[];
  workers: WorkerCard[];
  active_invitation: CustomerInvitation | null;
}

export interface WorkerInvitation {
  id: string;
  status: InvitationStatus;
  created_at: string;
  seen_at: string | null;
  closed_at: string | null;
  decline_reason: DeclineReason | null;
  job: SharedSummary;
}

export const fetchRecommendations = (jobId: string, signal?: AbortSignal) =>
  apiRequest<Recommendations>(`/jobs/${jobId}/recommendations/`, { signal });

export const fetchJobInvitations = (jobId: string, signal?: AbortSignal) =>
  apiRequest<{ results: CustomerInvitation[] }>(`/jobs/${jobId}/invitations/`, { signal });

export const sendInvitation = (jobId: string, workerId: string) =>
  apiRequest<CustomerInvitation>(`/jobs/${jobId}/invitations/`, { method: "POST", body: { worker_id: workerId } });

export const withdrawInvitation = (jobId: string, invitationId: string) =>
  apiRequest<CustomerInvitation>(`/jobs/${jobId}/invitations/${invitationId}/withdraw/`, { method: "POST" });

export const updateSharedDescription = (jobId: string, description: string) =>
  apiRequest<JobRequest & { privacy_warnings: string[] }>(`/jobs/${jobId}/shared-description/`, {
    method: "PATCH",
    body: { description },
  });

export const fetchInbox = (signal?: AbortSignal) => apiRequest<Page<WorkerInvitation>>("/invitations/?page_size=50", { signal });

export const fetchInvitation = (id: string, signal?: AbortSignal) => apiRequest<WorkerInvitation>(`/invitations/${id}/`, { signal });

export const declineInvitation = (id: string, reason?: DeclineReason) =>
  apiRequest<WorkerInvitation>(`/invitations/${id}/decline/`, { method: "POST", body: reason ? { reason } : {} });

/** Short, non-identifying reference for a worker card ("A7F3"). */
export const workerRef = (workerId: string) => workerId.replace(/-/g, "").slice(-4).toUpperCase();
