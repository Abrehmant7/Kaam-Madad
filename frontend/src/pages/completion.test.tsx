import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/resources/en";
import { AREAS, bootHandlers, errorEnvelope, jsonResponse, makeDashboard, makeUser, mockApi, SERVICES, TRADES, workerHandlers } from "../test/http";
import { renderApp } from "../test/renderApp";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const catalog = {
  "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
  "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
  "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
};
const SHARED = {
  description: "Two ceiling fans", trade: "electrician", services: ["elec_fan_install"], services_excluded: [], city: "islamabad",
  area: "isb-g-9", window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z", budget_preference_pkr: null, has_photos: false,
};
const TERMS = {
  inspection_only: false, scope: "Install two ceiling fans", quantity: 2, labour_amount: "600.00", labour_basis: "per_item", materials: "included",
  materials_amount: null, visit_fee: null, visit_fee_treatment: "none", exclusions: "", start_at: "2030-01-10T12:00:00Z", end_at: "2030-01-10T14:00:00Z",
  totals: { labour_total: "1200.00", materials_total: "0.00", visit_total: "0.00", known_total: "1200.00", unknown: [], complete: true },
};
const NO_ACTIONS = { arrive: false, issue_code: false, start: false, cancel: false, propose_change: false, change_time: false,
  request_completion: false, completion_blocked_by_change: false, confirm_completion: false, raise_issue: false, review: false };

type Fixture = Record<string, unknown> & { actions: Record<string, boolean> };
function booking(overrides: Record<string, unknown> = {}): Fixture {
  return {
    id: "b-1", status: "in_progress", role: "customer", invitation_id: "inv-1", job_id: "job-1", quote_id: "q-1", quote_version: 1,
    start_at: TERMS.start_at, end_at: TERMS.end_at, timezone: "Asia/Karachi", terms: { ...TERMS, source: { kind: "quote", version: 1 } },
    accepted_terms: { ...TERMS, quote_id: "q-1", version: 1, submitted_at: "x", accepted_at: "x", check: { status: "passed", provider: "fixture", simulated: true, manual_review_at: null }, resolutions: [] },
    terms_changed: false, job: SHARED, address: null, counterpart: { role: "customer" },
    created_at: "2030-01-01T10:00:00Z", arrived_at: "x", started_at: "x", cancelled_at: null, cancelled_role: null, cancel_reason: null, cancel_note: null,
    completion_requested_at: null, completed_at: null, completed_services: [], disputed_at: null, dispute_reason: null, dispute_note: null,
    closed_at: null, staff_outcome: null, staff_reason: null, review: null, contact_block: { blocked: false, by_me: false, block_id: null }, arrival_code: null, changes: [], history: [],
    actions: NO_ACTIONS, ...overrides,
  };
}
const customer = () => makeUser({ role: "customer", preferred_language: "en" });
const worker = () => makeUser({ role: "worker", preferred_language: "en" });

describe("completion", () => {
  it("an open change blocks the completion request, with an explanation", async () => {
    mockApi({
      ...bootHandlers(worker()), ...catalog,
      "GET /api/v1/bookings/b-1/": jsonResponse(booking({ role: "worker", actions: { ...NO_ACTIONS, request_completion: true, completion_blocked_by_change: true } })),
    });
    renderApp("/bookings/b-1", "en");
    expect(await screen.findByText(en["completion.changeOpen"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["completion.request"] })).toBeDisabled();
  });

  it("worker asks the customer to confirm and then waits", async () => {
    let current = booking({ role: "worker", actions: { ...NO_ACTIONS, request_completion: true } });
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      "GET /api/v1/bookings/b-1/": () => jsonResponse(current),
      "POST /api/v1/bookings/b-1/request-completion/": () => {
        current = { ...current, status: "completion_requested", completion_requested_at: "x", actions: NO_ACTIONS };
        return jsonResponse(current);
      },
    });
    renderApp("/bookings/b-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["completion.request"] }));
    expect(await screen.findByText(en["completion.waitingTitle"])).toBeInTheDocument();
    expect(calls.filter((call) => call.path.endsWith("/request-completion/"))).toHaveLength(1);
  });

  it("customer raises an issue with a reason and a note", async () => {
    let current = booking({ status: "completion_requested", completion_requested_at: "x", actions: { ...NO_ACTIONS, confirm_completion: true, raise_issue: true } });
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": () => jsonResponse(current),
      "POST /api/v1/bookings/b-1/raise-issue/": (init) => {
        const body = JSON.parse(String(init.body)) as { reason: string; note: string };
        current = { ...current, status: "disputed", disputed_at: "x", dispute_reason: body.reason, dispute_note: body.note, actions: NO_ACTIONS };
        return jsonResponse(current);
      },
    });
    renderApp("/bookings/b-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["completion.raise"] }));
    const send = screen.getByRole("button", { name: en["completion.raiseConfirm"] });
    expect(send).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["completion.reason.not_finished"]) }));
    await userEvent.type(screen.getByLabelText(en["completion.noteLabel"]), "One fan does not turn");
    await userEvent.click(send);
    expect(await screen.findByText(en["completion.disputedTitle"])).toBeInTheDocument();
    expect(screen.getByText("“One fan does not turn”")).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/raise-issue/"))?.body).toEqual({ reason: "not_finished", note: "One fan does not turn" });
  });

  it("customer confirms, then leaves one review with an approved text", async () => {
    let current = booking({ status: "completion_requested", completion_requested_at: "x", actions: { ...NO_ACTIONS, confirm_completion: true, raise_issue: true } });
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": () => jsonResponse(current),
      "POST /api/v1/bookings/b-1/confirm-completion/": () => {
        current = { ...current, status: "completed", completed_at: "x", completed_services: ["elec_fan_install"], actions: { ...NO_ACTIONS, review: true } };
        return jsonResponse(current);
      },
      "POST /api/v1/bookings/b-1/review/": (init) => {
        const body = JSON.parse(String(init.body)) as { rating: number; text: string };
        const review = { id: "r-1", rating: body.rating, text: body.text, source: "typed", services: ["elec_fan_install"], created_at: "x", hidden: false };
        current = { ...current, review, actions: NO_ACTIONS };
        return jsonResponse({ ...review, created: true }, 201);
      },
    });
    renderApp("/bookings/b-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["completion.confirm"] }));
    expect(await screen.findByText(en["review.title"])).toBeInTheDocument();
    const send = screen.getByRole("button", { name: en["review.submit"] });
    expect(send).toBeDisabled(); // a rating is required
    await userEvent.click(screen.getByRole("radio", { name: en["review.starsLabel"].replace("{rating}", "4") }));
    await userEvent.type(screen.getByLabelText(en["review.textLabel"]), "Neat work, on time");
    await userEvent.click(send);
    expect(await screen.findByText(en["review.yours"])).toBeInTheDocument();
    expect(screen.getByText("“Neat work, on time”")).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/review/"))?.body).toEqual({ rating: 4, text: "Neat work, on time" });
  });

  it("a review refused by the server shows why", async () => {
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": jsonResponse(booking({ status: "completed", completed_at: "x", actions: { ...NO_ACTIONS, review: true } })),
      "POST /api/v1/bookings/b-1/review/": jsonResponse(errorEnvelope("review_not_allowed", "r1", { status: "closed" }), 409),
    });
    renderApp("/bookings/b-1", "en");
    await userEvent.click(await screen.findByRole("radio", { name: en["review.starsLabel"].replace("{rating}", "5") }));
    await userEvent.click(screen.getByRole("button", { name: en["review.submit"] }));
    expect(await screen.findByText(en["errors.review_not_allowed"])).toBeInTheDocument();
  });
});

describe("worker dashboard history", () => {
  it("shows Performance from the server totals and the feedback per completed job", async () => {
    mockApi({
      ...bootHandlers(worker()), ...catalog,
      ...workerHandlers(makeDashboard(null)),
      "GET /api/v1/invitations/": jsonResponse(page([])),
      "GET /api/v1/bookings/": jsonResponse(page([])),
      "GET /api/v1/workers/me/stats/": jsonResponse({
        invitations_received: 57, completed_jobs: 2, review_count: 1, average_rating: "4.0",
        rating_distribution: [{ stars: 5, count: 0 }, { stars: 4, count: 1 }, { stars: 3, count: 0 }, { stars: 2, count: 0 }, { stars: 1, count: 0 }],
      }),
      "GET /api/v1/bookings/feedback/": jsonResponse({
        completed_jobs: 2, review_count: 1, average_rating: "4.0",
        jobs: [
          { booking_id: "b-1", completed_at: "2030-01-10T15:00:00Z", trade: "electrician", area: "isb-g-9", services: ["elec_fan_install"],
            review: { id: "r-1", rating: 4, text: "Neat work", source: "typed", services: ["elec_fan_install"], created_at: "x", hidden: false } },
          { booking_id: "b-2", completed_at: "2030-01-12T15:00:00Z", trade: "electrician", area: "isb-g-9", services: ["elec_fan_install"], review: null },
        ],
      }),
    });
    renderApp("/worker", "en");
    expect(await screen.findByText(en["feedback.heading"])).toBeInTheDocument();
    const performance = within(await screen.findByRole("region", { name: en["perf.heading"] }));
    expect(await performance.findByText("4.0")).toBeInTheDocument();
    expect(performance.getByText(en["feedback.reviewCount"].replace("{count}", "1"))).toBeInTheDocument();
    // Exact counts beside each bar: lifetime invitations (more than one page) and completed jobs.
    const invitations = performance.getByText(en["perf.invitations"]).closest("div")!;
    expect(within(invitations).getByText("57")).toBeInTheDocument();
    expect(within(performance.getByText(en["perf.completed"]).closest("div")!).getByText("2")).toBeInTheDocument();
    const fourStars = performance.getByLabelText(en["perf.stars"].replace("{count}", "4")).closest("li")!;
    expect(within(fourStars).getByText("1")).toBeInTheDocument();
    expect(screen.getByText("“Neat work”")).toBeInTheDocument();
    expect(screen.getByText(en["feedback.noReviewForJob"])).toBeInTheDocument();
    expect(screen.queryByText(en["rec.noReviews"])).not.toBeInTheDocument();
  });
});
