import type { BookingLink } from "./invitations";
import { apiRequest } from "./client";
import type { Page } from "./catalog";

export type JobStatus = "draft" | "confirmed";

export interface JobDetails {
  description: string;
  trade: string | null;
  services: string[];
  services_excluded: string[];
  city: string | null;
  area: string | null;
  /** The time as the customer said it ("kal shaam"); never turned into a time automatically. */
  preferred_time_text: string;
  /** UTC ISO timestamps; shown in Asia/Karachi. */
  window_start: string | null;
  window_end: string | null;
  timezone: "Asia/Karachi";
  /** Private to the customer: never read aloud, never in matching summaries. */
  address_private: string;
  access_notes: string;
  /** The customer's preference in PKR (decimal string), not a quote. */
  budget_pkr: string | null;
}

export interface JobPhoto {
  id: string;
  mime_type: string;
  width: number;
  height: number;
  size_bytes: number;
  content_url: string;
}

export interface JobSuggestions {
  interpretation_id: string;
  provider: string;
  simulated: boolean;
  fields: Record<string, unknown>;
  missing: string[];
  uncertain: string[];
  unmatched_mentions: { phrase: string; negated: boolean }[];
  heard: Record<string, string>;
}

export interface JobRequest {
  id: string;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  confirmed_at: string | null;
  source: {
    kind: "text" | "voice";
    language: string | null;
    /** Untouched original input (typed text or transcript). */
    original_text: string;
    audio_clip_id: string | null;
    transcription_id: string | null;
  };
  details: JobDetails;
  suggestions: JobSuggestions | null;
  photos: JobPhoto[];
  /** What still blocks confirmation, as field → codes. */
  issues: Record<string, string[]>;
  ready_to_confirm: boolean;
  already_confirmed?: boolean;
  booking: BookingLink | null;
}

export interface JobListItem {
  id: string;
  status: JobStatus;
  description: string;
  trade: string | null;
  services: string[];
  city: string | null;
  area: string | null;
  window_start: string | null;
  window_end: string | null;
  updated_at: string;
  confirmed_at: string | null;
  booking: BookingLink | null;
}

export type DetailsPatch = Partial<Omit<JobDetails, "timezone">>;

export const listJobs = (signal?: AbortSignal) => apiRequest<Page<JobListItem>>("/jobs/?page_size=50", { signal });

export const createTextJob = (original_text: string, source_language: "ur" | "en") =>
  apiRequest<JobRequest>("/jobs/", { method: "POST", body: { source_kind: "text", original_text, source_language } });

export const createVoiceJob = (audio_clip_id: string, source_language: "ur" | "en") =>
  apiRequest<JobRequest>("/jobs/", { method: "POST", body: { source_kind: "voice", audio_clip_id, source_language } });

export const fetchJob = (id: string, signal?: AbortSignal) => apiRequest<JobRequest>(`/jobs/${id}/`, { signal });

export const saveJob = (id: string, details: DetailsPatch) =>
  apiRequest<JobRequest>(`/jobs/${id}/`, { method: "PATCH", body: details });

export const attachSource = (id: string, source: { transcription_id?: string; interpretation_id?: string }) =>
  apiRequest<JobRequest>(`/jobs/${id}/source/`, { method: "POST", body: source });

export const confirmJob = (id: string) => apiRequest<JobRequest>(`/jobs/${id}/confirm/`, { method: "POST" });

export const deleteJob = (id: string) => apiRequest<void>(`/jobs/${id}/`, { method: "DELETE" });

export function uploadJobPhoto(id: string, file: Blob, name: string) {
  const form = new FormData();
  form.append("image", file, name);
  return apiRequest<JobPhoto>(`/jobs/${id}/photos/`, { method: "POST", body: form, timeoutMs: 60_000 });
}

export const deleteJobPhoto = (id: string, photoId: string) =>
  apiRequest<void>(`/jobs/${id}/photos/${photoId}/`, { method: "DELETE" });

export const fetchJobPhoto = (contentUrl: string) =>
  apiRequest<Blob>(contentUrl.replace(/^\/api\/v1/, ""), { responseType: "blob" });
