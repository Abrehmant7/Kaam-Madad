import type { Page } from "./catalog";
import { apiRequest } from "./client";
import type { Materials, Quote, QuoteTerms, VisitFeeTreatment } from "./conversations";
import type { SharedSummary } from "./invitations";

export type BookingStatus = "confirmed" | "arrived" | "in_progress" | "completion_requested" | "completed" | "disputed" | "closed" | "cancelled";
export type DisputeReason = "not_finished" | "not_as_agreed" | "damage" | "price" | "other";

export interface Review {
  id: string;
  rating: number;
  text: string;
  source: "typed" | "voice";
  services: string[];
  created_at: string;
  hidden: boolean;
  /** Only for the author: the automatic proposal from their recording. */
  interpreted_text?: string | null;
  created?: boolean;
}
export type CancelReason = "not_available" | "changed_plans" | "no_show" | "other";

/** Structured terms as stored on a booking (amounts are PKR decimal strings; times UTC "…Z"). */
export interface BookingTerms {
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
  start_at: string;
  end_at: string;
  totals: NonNullable<Quote["totals"]>;
  source?: { kind: "quote"; version: number } | { kind: "change"; number: number };
}

export interface AcceptedTerms extends BookingTerms {
  quote_id: string;
  version: number;
  submitted_at: string;
  accepted_at: string;
  check: { status: string; provider: string | null; simulated: boolean; manual_review_at: string | null };
  resolutions: { code: string; source: string; resolution: string | null; note: string | null; resolved_role: string | null; status: string }[];
}

export interface BookingChange {
  id: string;
  number: number;
  status: "pending" | "approved" | "rejected" | "withdrawn" | "void";
  proposed_role: "customer" | "worker";
  note: string;
  old_terms: BookingTerms;
  new_terms: BookingTerms;
  customer_approved_at: string | null;
  worker_approved_at: string | null;
  decided_at: string | null;
  decided_role: "customer" | "worker" | null;
  created_at: string;
  can_approve: boolean;
  can_withdraw: boolean;
}

export interface BookingEvent {
  kind: "confirmed" | "arrived" | "code_issued" | "started" | "cancelled" | "change_proposed" | "change_approved" | "change_rejected"
    | "change_withdrawn" | "completion_requested" | "completed" | "disputed" | "staff_resolved" | "reviewed";
  from_status: BookingStatus | null;
  to_status: BookingStatus | null;
  actor_role: "customer" | "worker" | "staff" | null;
  note: string | null;
  data: Record<string, unknown>;
  at: string;
}

/** Whether an arrival code is active. Never contains the code itself. */
export interface ArrivalCodeState {
  active: boolean;
  issued_at?: string;
  expires_at?: string;
  attempts_remaining?: number;
  expired?: boolean;
  locked?: boolean;
  used_at: string | null;
}

export interface Booking {
  id: string;
  status: BookingStatus;
  role: "customer" | "worker";
  invitation_id: string;
  job_id: string | null;
  quote_id: string;
  quote_version: number;
  start_at: string;
  end_at: string;
  timezone: "Asia/Karachi";
  terms: BookingTerms;
  accepted_terms: AcceptedTerms;
  terms_changed: boolean;
  job: SharedSummary;
  /** The exact address: the customer's own, or for the assigned worker while the booking is open. */
  address: { address: string; access_notes: string } | null;
  counterpart: { role: "worker"; worker_id: string; trade: string | null; verification: { status: string | null; simulated: boolean } } | { role: "customer" };
  created_at: string;
  arrived_at: string | null;
  started_at: string | null;
  cancelled_at: string | null;
  cancelled_role: "customer" | "worker" | null;
  cancel_reason: CancelReason | null;
  cancel_note: string | null;
  completion_requested_at: string | null;
  completed_at: string | null;
  completed_services: string[];
  disputed_at: string | null;
  dispute_reason: DisputeReason | null;
  dispute_note: string | null;
  closed_at: string | null;
  staff_outcome: "return_to_work" | "close" | null;
  staff_reason: string | null;
  review: Review | null;
  arrival_code: ArrivalCodeState | null;
  changes: BookingChange[];
  history: BookingEvent[];
  actions: {
    arrive: boolean; issue_code: boolean; start: boolean; cancel: boolean; propose_change: boolean; change_time: boolean;
    request_completion: boolean; completion_blocked_by_change: boolean; confirm_completion: boolean; raise_issue: boolean; review: boolean;
  };
  created?: boolean;
  /** Only in the response to issuing a code (customer). */
  code?: { value: string; expires_at: string };
}

export interface BookingCard {
  id: string;
  status: BookingStatus;
  role: "customer" | "worker";
  start_at: string;
  end_at: string;
  trade: string | null;
  services: string[];
  area: string | null;
  known_total: string | null;
  complete: boolean;
  quote_version: number;
  invitation_id: string;
  worker_id: string | null;
  review_submitted: boolean;
}

export interface WorkerFeedback {
  completed_jobs: number;
  review_count: number;
  /** One decimal ("4.5"), or null when there are no visible reviews (never zero). */
  average_rating: string | null;
  jobs: { booking_id: string; completed_at: string; trade: string | null; area: string | null; services: string[]; review: Review | null }[];
}

export const listBookings = (signal?: AbortSignal) => apiRequest<Page<BookingCard>>("/bookings/?page_size=50", { signal });

export const fetchBooking = (id: string, signal?: AbortSignal) => apiRequest<Booking>(`/bookings/${id}/`, { signal });

export interface AcceptPayload {
  invitation_id: string;
  quote_id: string;
  version: number;
  /** Generated on this device and kept until the outcome is known, so a retry can never book twice. */
  idempotency_key: string;
}

export const acceptQuote = (payload: AcceptPayload) =>
  apiRequest<Booking>("/bookings/", { method: "POST", body: payload, timeoutMs: 20_000 });

export const markArrived = (id: string) => apiRequest<Booking>(`/bookings/${id}/arrive/`, { method: "POST" });

export const issueArrivalCode = (id: string) => apiRequest<Booking>(`/bookings/${id}/arrival-code/`, { method: "POST" });

export const startWithCode = (id: string, code: string) =>
  apiRequest<Booking>(`/bookings/${id}/start/`, { method: "POST", body: { code } });

export const cancelBooking = (id: string, reason: CancelReason, note: string) =>
  apiRequest<Booking>(`/bookings/${id}/cancel/`, { method: "POST", body: { reason, note } });

export const proposeChange = (id: string, terms: QuoteTerms, note: string) =>
  apiRequest<Booking>(`/bookings/${id}/changes/`, { method: "POST", body: { ...terms, materials: terms.materials ?? "", note } });

export const decideChange = (id: string, changeId: string, action: "approve" | "reject" | "withdraw") =>
  apiRequest<Booking>(`/bookings/${id}/changes/${changeId}/${action}/`, { method: "POST" });

export const requestCompletion = (id: string) => apiRequest<Booking>(`/bookings/${id}/request-completion/`, { method: "POST" });

export const confirmCompletion = (id: string) => apiRequest<Booking>(`/bookings/${id}/confirm-completion/`, { method: "POST" });

export const raiseIssue = (id: string, reason: DisputeReason, note: string) =>
  apiRequest<Booking>(`/bookings/${id}/raise-issue/`, { method: "POST", body: { reason, note } });

export interface ReviewPayload { rating: number; text: string; audio_clip_id?: string; transcription_id?: string }

export const submitReview = (id: string, payload: ReviewPayload) =>
  apiRequest<Review>(`/bookings/${id}/review/`, { method: "POST", body: payload });

export const fetchFeedback = (signal?: AbortSignal) => apiRequest<WorkerFeedback>("/bookings/feedback/", { signal });

const KEY_PREFIX = "km-accept-";

/** The acceptance key for one quote version, kept in this tab until the outcome is known. */
export function acceptanceKey(quoteId: string): string {
  try {
    const stored = window.sessionStorage.getItem(KEY_PREFIX + quoteId);
    if (stored) return stored;
    const fresh = crypto.randomUUID();
    window.sessionStorage.setItem(KEY_PREFIX + quoteId, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

export function forgetAcceptanceKey(quoteId: string): void {
  try {
    window.sessionStorage.removeItem(KEY_PREFIX + quoteId);
  } catch {
    /* storage unavailable: nothing to forget */
  }
}
