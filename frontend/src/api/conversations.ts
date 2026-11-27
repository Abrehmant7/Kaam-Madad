import { apiRequest } from "./client";
import type { SharedSummary } from "./invitations";

const base = (id: string) => `/conversations/${id}`;

export interface ConversationHeader {
  invitation: { id: string; status: "active" | "declined" | "withdrawn"; created_at: string; closed_at: string | null };
  role: "customer" | "worker";
  can_write: boolean;
  job: SharedSummary;
  job_id: string | null;
  counterpart: { role: "worker"; worker_id: string; trade: string | null } | { role: "customer" };
}

export interface Message {
  id: string;
  client_id: string | null;
  sender_role: "customer" | "worker";
  mine: boolean;
  kind: "text" | "voice";
  text: string;
  caption_status: "approved" | "typed" | "unavailable" | null;
  interpreted_text: string | null;
  audio_url: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface Finding {
  id: string;
  source: "rule" | "ai";
  code: string;
  blocking: boolean;
  question: string;
  ask: "worker" | "customer" | "both";
  sources: { kind: "request" | "message" | "quote"; ref: string; text: string }[];
  status: "open" | "resolved";
  resolution: "clarified" | "not_a_conflict" | null;
  resolution_note: string | null;
  resolved_role: "customer" | "worker" | null;
  resolved_at: string | null;
}

export type Materials = "included" | "worker_extra" | "customer" | "none";
export type VisitFeeTreatment = "none" | "charged" | "waived_if_hired" | "included";

export interface QuoteTerms {
  inspection_only: boolean;
  scope: string;
  quantity: number | null;
  labour_amount: string | null;
  labour_basis: "total" | "per_item";
  materials: Materials | null;
  materials_amount: string | null;
  visit_fee: string | null;
  visit_fee_treatment: VisitFeeTreatment;
  exclusions: string;
  start_at: string | null;
  end_at: string | null;
}

export interface Quote extends QuoteTerms {
  id: string;
  version: number | null;
  status: "draft" | "submitted" | "superseded";
  timezone: "Asia/Karachi";
  totals: { labour_total: string | null; materials_total: string | null; visit_total: string | null; known_total: string; unknown: string[]; complete: boolean } | null;
  submitted_at: string | null;
  superseded_at: string | null;
  expires_at: string | null;
  expired: boolean;
  check: { status: "not_run" | "passed" | "findings" | "unavailable"; provider: string | null; simulated: boolean; checked_at: string | null; failure: string | null };
  manual_review_at: string | null;
  findings: Finding[];
  issues: Record<string, string[]>;
}

export interface Readiness {
  invitation_id: string;
  quote_id: string | null;
  version: number | null;
  expires_at: string | null;
  ready: boolean;
  blocking: string[];
  warnings: string[];
}

export interface QuotesListing {
  current: Quote | null;
  draft: Quote | null;
  history: Quote[];
  readiness: Readiness;
}

export const fetchConversation = (id: string, signal?: AbortSignal) => apiRequest<ConversationHeader>(`${base(id)}/`, { signal });

export function fetchMessages(id: string, cursor: { after?: string; before?: string } = {}, signal?: AbortSignal) {
  const query = cursor.after ? `?after=${cursor.after}` : cursor.before ? `?before=${cursor.before}` : "";
  return apiRequest<{ results: Message[]; has_more_before: boolean | null }>(`${base(id)}/messages/${query}`, { signal });
}

export interface SendPayload {
  client_id: string;
  kind: "text" | "voice";
  text?: string;
  audio_clip_id?: string;
  transcription_id?: string;
}

export const sendMessage = (id: string, payload: SendPayload) =>
  apiRequest<Message>(`${base(id)}/messages/`, { method: "POST", body: payload });

export const fetchMessageAudio = (url: string) => apiRequest<Blob>(url.replace(/^\/api\/v1/, ""), { responseType: "blob" });

export const fetchQuotes = (id: string, signal?: AbortSignal) => apiRequest<QuotesListing>(`${base(id)}/quotes/`, { signal });

/** Save the worker's draft (all fields). "No materials choice yet" is sent as "" as the API expects. */
export const saveDraft = (id: string, terms: QuoteTerms) =>
  apiRequest<Quote>(`${base(id)}/quotes/draft/`, { method: "PUT", body: { ...terms, materials: terms.materials ?? "" } });

export const deleteDraft = (id: string) => apiRequest<void>(`${base(id)}/quotes/draft/`, { method: "DELETE" });

export const submitDraft = (id: string) =>
  apiRequest<Quote>(`${base(id)}/quotes/draft/submit/`, { method: "POST", timeoutMs: 60_000 });

export const rerunCheck = (id: string, quoteId: string) =>
  apiRequest<Quote & { readiness: Readiness }>(`${base(id)}/quotes/${quoteId}/check/`, { method: "POST", timeoutMs: 60_000 });

export const resolveFinding = (id: string, quoteId: string, findingId: string, resolution: "clarified" | "not_a_conflict", note: string) =>
  apiRequest<Quote & { readiness: Readiness }>(`${base(id)}/quotes/${quoteId}/findings/${findingId}/resolve/`, {
    method: "POST",
    body: { resolution, note },
  });

export const manualReview = (id: string, quoteId: string) =>
  apiRequest<Quote & { readiness: Readiness }>(`${base(id)}/quotes/${quoteId}/manual-review/`, { method: "POST" });

/** A send ID generated on this device; kept until the send succeeds so retries are safe. */
export function newClientId(): string {
  return crypto.randomUUID();
}
