import type { Page } from "./catalog";
import { apiRequest } from "./client";

export type ReportCategory = "harassment" | "threats" | "impersonation" | "no_show" | "property_work" | "other";
export type ReportStatus = "open" | "reviewing" | "resolved" | "dismissed";

export interface ReportEvidence {
  id: string;
  kind: "image" | "audio";
  role: "statement" | "evidence";
  mime_type: string;
  size_bytes: number;
  created_at: string;
  removed: boolean;
  content_url: string | null;
}

export interface ReportSummary {
  id: string;
  status: ReportStatus;
  category: ReportCategory;
  reporter_role: "customer" | "worker";
  interaction: { invitation_id: string; booking_id: string | null };
  awaiting_reply: boolean;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

/** The reporter's own view: never internal staff notes, never anything about who handled it. */
export interface Report extends ReportSummary {
  description: string;
  evidence: ReportEvidence[];
  messages: { from: "you" | "staff"; text: string; at: string }[];
  can_reply: boolean;
  can_add_evidence: boolean;
  created?: boolean;
}

export interface FilePayload {
  client_id: string;
  category: ReportCategory;
  description: string;
  invitation_id?: string;
  booking_id?: string;
  audio_clip_id?: string;
}

export const fileReport = (payload: FilePayload) => apiRequest<Report>("/reports/", { method: "POST", body: payload, timeoutMs: 20_000 });

export const listReports = (signal?: AbortSignal) => apiRequest<Page<ReportSummary>>("/reports/?page_size=50", { signal });

export const fetchReport = (id: string, signal?: AbortSignal) => apiRequest<Report>(`/reports/${id}/`, { signal });

export function addImageEvidence(id: string, file: Blob, filename: string) {
  const form = new FormData();
  form.append("file", file, filename);
  return apiRequest<Report>(`/reports/${id}/evidence/`, { method: "POST", body: form, timeoutMs: 30_000 });
}

export const addAudioEvidence = (id: string, audioClipId: string) =>
  apiRequest<Report>(`/reports/${id}/evidence/`, { method: "POST", body: { audio_clip_id: audioClipId } });

export const fetchEvidence = (url: string) => apiRequest<Blob>(url.replace(/^\/api\/v1/, ""), { responseType: "blob" });

export const replyToReport = (id: string, text: string) =>
  apiRequest<Report>(`/reports/${id}/replies/`, { method: "POST", body: { text } });

export const blockContact = (target: { invitation_id: string } | { booking_id: string }) =>
  apiRequest<{ id: string; created_at: string }>("/blocks/", { method: "POST", body: target });

export const unblockContact = (blockId: string) => apiRequest<void>(`/blocks/${blockId}/`, { method: "DELETE" });

export interface ContactBlockState {
  blocked: boolean;
  /** True only for the person who blocked; the other side only learns that contact is blocked. */
  by_me: boolean;
  block_id: string | null;
}
