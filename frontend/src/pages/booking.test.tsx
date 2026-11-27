import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/resources/en";
import { AREAS, bootHandlers, errorEnvelope, jsonResponse, makeUser, mockApi, SERVICES, TRADES } from "../test/http";
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
const TOTALS = { labour_total: "1200.00", materials_total: null, visit_total: "0.00", known_total: "1200.00", unknown: ["materials"], complete: false };
const TERMS = {
  inspection_only: false, scope: "Install two ceiling fans", quantity: 2, labour_amount: "600.00", labour_basis: "per_item",
  materials: "worker_extra", materials_amount: null, visit_fee: null, visit_fee_treatment: "none", exclusions: "",
  start_at: "2030-01-10T12:00:00Z", end_at: "2030-01-10T14:00:00Z", totals: TOTALS,
};
const quote = {
  id: "q-1", version: 2, status: "submitted", timezone: "Asia/Karachi", ...TERMS, submitted_at: "x", superseded_at: null,
  expires_at: "2030-01-02T11:00:00Z", expired: false, manual_review_at: null, findings: [], issues: {},
  check: { status: "passed", provider: "fixture", simulated: true, checked_at: "x", started_at: null, failure: null },
};
const readiness = { invitation_id: "inv-1", quote_id: "q-1", version: 2, expires_at: "2030-01-02T11:00:00Z", ready: true, blocking: [], warnings: ["unknown_amounts"], booking_id: null };
const header = (booking: unknown = null) => ({
  invitation: { id: "inv-1", status: "active", created_at: "x", closed_at: null }, role: "customer", can_write: true, job: SHARED,
  job_id: "job-1", booking, counterpart: { role: "worker", worker_id: "00000000-0000-4000-8000-00000000a7f3", trade: "electrician" },
});

/** A loose fixture: tests replace any field while a mocked flow moves the booking through its states. */
type Fixture = Record<string, unknown> & { actions: Record<string, boolean> };

function booking(overrides: Record<string, unknown> = {}): Fixture {
  return {
    id: "b-1", status: "confirmed", role: "customer", invitation_id: "inv-1", job_id: "job-1", quote_id: "q-1", quote_version: 2,
    start_at: TERMS.start_at, end_at: TERMS.end_at, timezone: "Asia/Karachi",
    terms: { ...TERMS, source: { kind: "quote", version: 2 } }, accepted_terms: { ...TERMS, quote_id: "q-1", version: 2, submitted_at: "x", accepted_at: "x",
      check: { status: "passed", provider: "fixture", simulated: true, manual_review_at: null }, resolutions: [] },
    terms_changed: false, job: SHARED, address: { address: "House 5, Street 9", access_notes: "Ring twice" },
    counterpart: { role: "worker", worker_id: "00000000-0000-4000-8000-00000000a7f3", trade: "electrician", verification: { status: "demo_approved", simulated: true } },
    created_at: "2030-01-01T10:00:00Z", arrived_at: null, started_at: null, cancelled_at: null, cancelled_role: null, cancel_reason: null, cancel_note: null,
    arrival_code: null, changes: [], history: [{ kind: "confirmed", from_status: null, to_status: "confirmed", actor_role: "customer", note: null, data: {}, at: "2030-01-01T10:00:00Z" }],
    actions: { arrive: false, issue_code: false, start: false, cancel: true, propose_change: true, change_time: true },
    ...overrides,
  };
}
const customer = () => makeUser({ role: "customer", preferred_language: "en" });
const worker = () => makeUser({ role: "worker", preferred_language: "en" });

describe("accepting a quote", () => {
  it("shows the exact terms and unknown costs, then books with an idempotency key", async () => {
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/conversations/inv-1/": jsonResponse(header()),
      "GET /api/v1/conversations/inv-1/quotes/": jsonResponse({ current: quote, draft: null, history: [], readiness }),
      "GET /api/v1/conversations/inv-1/messages/": jsonResponse({ results: [], has_more_before: false }),
      "POST /api/v1/bookings/": jsonResponse({ ...booking(), created: true }, 201),
      "GET /api/v1/bookings/b-1/": jsonResponse(booking()),
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["accept.open"] }));
    const review = screen.getByRole("region", { name: en["accept.title"].replace("{version}", "2") });
    expect(within(review).getByText(en["accept.unknownPart.materials"])).toBeInTheDocument(); // unknown is never shown as zero
    expect(within(review).getByText("PKR 1,200")).toBeInTheDocument();
    expect(within(review).getByText(en["accept.next.address"])).toBeInTheDocument();
    await userEvent.click(within(review).getByRole("button", { name: en["accept.confirm"] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/bookings/b-1"));
    const post = calls.find((call) => call.method === "POST" && call.path === "/api/v1/bookings/")!;
    expect(post.body).toMatchObject({ invitation_id: "inv-1", quote_id: "q-1", version: 2 });
    expect((post.body as { idempotency_key: string }).idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByRole("heading", { level: 1, name: en["booking.title"] })).toBeInTheDocument();
  }, 15000);

  it("after a dropped connection it reloads the server state before offering to try again with the same key", async () => {
    let posts = 0;
    let headers = 0;
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/conversations/inv-1/": () => jsonResponse(header(++headers > 2 ? { id: "b-1", status: "confirmed" } : null)),
      "GET /api/v1/conversations/inv-1/quotes/": jsonResponse({ current: quote, draft: null, history: [], readiness }),
      "GET /api/v1/conversations/inv-1/messages/": jsonResponse({ results: [], has_more_before: false }),
      "POST /api/v1/bookings/": () => { posts += 1; throw new TypeError("Failed to fetch"); },
      "GET /api/v1/bookings/b-1/": jsonResponse(booking()),
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["accept.open"] }));
    await userEvent.click(screen.getByRole("button", { name: en["accept.confirm"] }));
    expect(await screen.findByText(en["accept.unconfirmedTitle"])).toBeInTheDocument(); // server says: not booked yet
    await userEvent.click(screen.getByRole("button", { name: en["accept.retry"] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/bookings/b-1")); // the lost request had booked it
    const keys = calls.filter((call) => call.method === "POST" && call.path === "/api/v1/bookings/").map((call) => (call.body as { idempotency_key: string }).idempotency_key);
    expect(posts).toBe(2);
    expect(new Set(keys).size).toBe(1); // a retry can never create a second booking
  }, 15000);

  it("a stale quote shows the conflict and reloads the quotes", async () => {
    let loads = 0;
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/conversations/inv-1/": jsonResponse(header()),
      "GET /api/v1/conversations/inv-1/quotes/": () => { loads += 1; return jsonResponse({ current: quote, draft: null, history: [], readiness }); },
      "GET /api/v1/conversations/inv-1/messages/": jsonResponse({ results: [], has_more_before: false }),
      "POST /api/v1/bookings/": jsonResponse(errorEnvelope("quote_not_current", "r1", { current_quote_id: "q-2", current_version: 3 }), 409),
    });
    renderApp("/conversations/inv-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["accept.open"] }));
    const before = loads;
    await userEvent.click(screen.getByRole("button", { name: en["accept.confirm"] }));
    expect(await screen.findByText(en["errors.quote_not_current"])).toBeInTheDocument();
    await waitFor(() => expect(loads).toBeGreaterThan(before));
  });
});

describe("booking screen", () => {
  it("worker: arrive, then a wrong code shows attempts left, then the right code starts the job", async () => {
    let current = booking({ role: "worker", job_id: null, counterpart: { role: "customer" }, actions: { arrive: true, issue_code: false, start: false, cancel: true, propose_change: true, change_time: true } });
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      "GET /api/v1/bookings/b-1/": () => jsonResponse(current),
      "POST /api/v1/bookings/b-1/arrive/": () => {
        current = { ...current, status: "arrived", arrived_at: "x", actions: { ...current.actions, arrive: false, start: true },
                    arrival_code: { active: true, attempts_remaining: 5, expires_at: "2030-01-10T12:15:00Z", expired: false, locked: false, used_at: null } };
        return jsonResponse(current);
      },
      "POST /api/v1/bookings/b-1/start/": (init) => {
        const { code } = JSON.parse(String(init.body)) as { code: string };
        if (code !== "482913") return jsonResponse(errorEnvelope("code_incorrect", "r2", { attempts_remaining: 4 }), 400);
        current = { ...current, status: "in_progress", started_at: "x", actions: { ...current.actions, start: false, cancel: false } };
        return jsonResponse(current);
      },
    });
    renderApp("/bookings/b-1", "en");
    expect(await screen.findByText(en["booking.addressWorker"])).toBeInTheDocument();
    expect(screen.getByText("House 5, Street 9")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["arrival.markArrived"] }));
    const field = await screen.findByLabelText(en["arrival.codeLabel"]);
    await userEvent.type(field, "111111");
    await userEvent.click(screen.getByRole("button", { name: en["arrival.start"] }));
    expect(await screen.findByText(en["arrival.attemptsLeft"].replace("{count}", "4"))).toBeInTheDocument();
    expect(screen.getByText(en["errors.code_incorrect"].replace("{attempts}", "4"))).toBeInTheDocument();
    await userEvent.clear(field);
    await userEvent.type(field, "482 913");
    await userEvent.click(screen.getByRole("button", { name: en["arrival.start"] }));
    expect(await screen.findByText(en["booking.inProgressTitle"])).toBeInTheDocument();
    expect(calls.filter((call) => call.path.endsWith("/start/")).map((call) => call.body)).toEqual([{ code: "111111" }, { code: "482913" }]);
  }, 15000);

  it("customer: the code is shown once after arrival, with what it does and does not prove", async () => {
    const arrived = booking({ status: "arrived", arrived_at: "x", actions: { arrive: false, issue_code: true, start: false, cancel: true, propose_change: true, change_time: false } });
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": jsonResponse(arrived),
      "POST /api/v1/bookings/b-1/arrival-code/": jsonResponse({ ...arrived, code: { value: "482913", expires_at: "2030-01-10T12:15:00Z" },
        arrival_code: { active: true, attempts_remaining: 5, expires_at: "2030-01-10T12:15:00Z", expired: false, locked: false, used_at: null } }),
    });
    renderApp("/bookings/b-1", "en");
    expect(await screen.findByText(en["arrival.limits"])).toBeInTheDocument();
    expect(screen.queryByText("482913")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["arrival.showCode"] }));
    expect(await screen.findByText("482913")).toBeInTheDocument();
    expect(screen.getByText(en["arrival.shownOnce"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["arrival.newCode"] })).toBeInTheDocument();
  });

  it("a pending change shows old and new terms and needs this person's approval", async () => {
    const change = {
      id: "c-1", number: 1, status: "pending", proposed_role: "worker", note: "A third fan", old_terms: TERMS,
      new_terms: { ...TERMS, quantity: 3, totals: { ...TOTALS, labour_total: "1800.00", known_total: "1800.00" } },
      customer_approved_at: null, worker_approved_at: "x", decided_at: null, decided_role: null, created_at: "x", can_approve: true, can_withdraw: false,
    };
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": jsonResponse(booking({ changes: [change], actions: { ...booking().actions, propose_change: false } })),
      "POST /api/v1/bookings/b-1/changes/c-1/approve/": jsonResponse(booking({ changes: [{ ...change, status: "approved", can_approve: false }], terms_changed: true,
        terms: { ...change.new_terms, source: { kind: "change", number: 1 } } })),
    });
    renderApp("/bookings/b-1", "en");
    expect(await screen.findByText(en["change.pending"].replace("{number}", "1"))).toBeInTheDocument();
    expect(screen.getByText(en["change.stillInEffect"])).toBeInTheDocument();
    expect(screen.getAllByText(en["quote.field.quantity"]).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: en["change.approve"] }));
    expect(await screen.findByText(en["booking.termsAfterChange"].replace("{number}", "1"))).toBeInTheDocument();
    expect(screen.getByText(en["booking.original"].replace("{version}", "2"))).toBeInTheDocument(); // the original stays visible
    expect(calls.some((call) => call.path.endsWith("/changes/c-1/approve/"))).toBe(true);
  });

  it("cancelling needs a reason and shows the result", async () => {
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/bookings/b-1/": jsonResponse(booking()),
      "POST /api/v1/bookings/b-1/cancel/": jsonResponse(booking({ status: "cancelled", cancelled_at: "x", cancelled_role: "customer", cancel_reason: "changed_plans",
        address: { address: "House 5, Street 9", access_notes: "Ring twice" }, actions: { arrive: false, issue_code: false, start: false, cancel: false, propose_change: false, change_time: false } })),
    });
    renderApp("/bookings/b-1", "en");
    await userEvent.click(await screen.findByText(en["cancel.title"]));
    const confirm = screen.getByRole("button", { name: en["cancel.confirm"] });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["cancel.reason.changed_plans"]) }));
    await userEvent.click(confirm);
    expect(await screen.findByText(en["booking.cancelledTitle"].replace("{role}", en["conv.role.customer"]))).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/cancel/"))?.body).toEqual({ reason: "changed_plans", note: "" });
  });

  it("another account gets the not-found message", async () => {
    mockApi({ ...bootHandlers(customer()), ...catalog, "GET /api/v1/bookings/b-1/": jsonResponse(errorEnvelope("not_found", "r1"), 404) });
    renderApp("/bookings/b-1", "en");
    expect(await screen.findByText(en["errors.not_found"])).toBeInTheDocument();
  });
});
