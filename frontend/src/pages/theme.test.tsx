import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { customerNextStep, workerNextStep } from "../features/dashboard/NextStep";
import { en } from "../i18n/resources/en";
import { ur } from "../i18n/resources/ur";
import { AREAS, bootHandlers, jsonResponse, makeDashboard, makeUser, mockApi, SERVICES, TRADES, workerHandlers } from "../test/http";
import { renderApp } from "../test/renderApp";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const catalog = {
  "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
  "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
  "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
};
const booking = (status: string, role: "customer" | "worker", extra: Record<string, unknown> = {}) => ({
  id: `b-${status}`, status, role, start_at: "2030-01-10T12:00:00Z", end_at: "2030-01-10T14:00:00Z", trade: "electrician",
  services: ["elec_fan_install"], area: "isb-g-9", known_total: "1200.00", complete: true, quote_version: 1, invitation_id: "inv-1",
  worker_id: null, review_submitted: false, ...extra,
}) as never;

describe("navigation", () => {
  it("gives a worker role-aware destinations, a quick bar on phones, the language switch and the demo label", async () => {
    mockApi({ ...bootHandlers(makeUser({ preferred_language: "en" })), ...workerHandlers(makeDashboard(null)),
      "GET /api/v1/bookings/": jsonResponse(page([])) });
    renderApp("/worker", "en");
    await screen.findByRole("heading", { level: 1, name: en["worker.dashboard.title"] });
    const main = screen.getByRole("navigation", { name: en["nav.mainMenu"] });
    for (const [name, href] of [[en["nav.invitations"], "/worker#invitations"], [en["nav.bookings"], "/worker#bookings"],
      [en["nav.verify"], "/worker/verify"], [en["nav.reports"], "/reports"]]) {
      expect(within(main).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(within(main).queryByRole("link", { name: en["nav.newRequest"] })).not.toBeInTheDocument(); // customer-only
    const quick = screen.getByRole("navigation", { name: en["nav.quickMenu"] });
    expect(within(quick).getAllByRole("link")).toHaveLength(4);
    expect(within(quick).getByRole("link", { name: en["nav.home"] })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: en["nav.changeLanguage"].replace("{language}", "اردو") })).toBeInTheDocument();
    expect(screen.getByText(en["demo.banner"])).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: en["nav.logout"] })).toHaveLength(1);
  });

  it("gives a customer the request destinations", async () => {
    mockApi({ ...bootHandlers(makeUser({ role: "customer", preferred_language: "en" })), ...catalog,
      "GET /api/v1/jobs/": jsonResponse(page([])), "GET /api/v1/bookings/": jsonResponse(page([])) });
    renderApp("/customer", "en");
    await screen.findByRole("heading", { level: 1, name: en["home.customer.title"] });
    const quick = within(screen.getByRole("navigation", { name: en["nav.quickMenu"] }));
    expect(quick.getByRole("link", { name: en["nav.newRequest"] })).toHaveAttribute("href", "/customer/requests/new");
    expect(quick.getByRole("link", { name: en["nav.requests"] })).toHaveAttribute("href", "/customer#requests");
    expect(screen.queryByRole("link", { name: en["nav.invitations"] })).not.toBeInTheDocument();
    // Empty states, and the next step from the real (empty) account: describe a job.
    expect(await screen.findByText(en["next.customer.new.title"])).toBeInTheDocument();
    expect(screen.getByText(en["jobs.list.empty"])).toBeInTheDocument();
    expect(await screen.findByText(en["booking.list.empty"])).toBeInTheDocument();
  });
});

describe("next step (from the real account state)", () => {
  const dashboard = (overrides: Record<string, unknown> = {}) => makeDashboard(null, overrides) as never;
  const verified = { identity: { status: "demo_approved", counts_here: true } };

  it("worker: bookings first, then verification, invitations, the accepting switch", () => {
    expect(workerNextStep(dashboard(), [booking("in_progress", "worker")], []).key).toBe("worker.finish");
    expect(workerNextStep(dashboard(), [booking("confirmed", "worker")], []).to).toBe("/bookings/b-confirmed");
    expect(workerNextStep(dashboard(), [], []).key).toBe("worker.verify");
    const invite = { id: "inv-9", status: "active", booking: null } as never;
    expect(workerNextStep(dashboard(verified), [], [invite]).to).toBe("/worker/invitations/inv-9");
    const paused = dashboard({ ...verified, profile: { ...(makeDashboard(null).profile as object), accepting_requests: false } });
    expect(workerNextStep(paused, [], []).key).toBe("worker.paused");
    expect(workerNextStep(dashboard(verified), null, null).key).toBe("worker.idle"); // a failed load is not an error here
  });

  it("customer: booking actions, then drafts, then finding a worker, else describe a job", () => {
    expect(customerNextStep([], [booking("arrived", "customer")]).key).toBe("customer.code");
    expect(customerNextStep([], [booking("completed", "customer")]).key).toBe("customer.review");
    expect(customerNextStep([], [booking("completed", "customer", { review_submitted: true })]).key).toBe("customer.new");
    const draft = { id: "j1", status: "draft", booking: null } as never;
    const confirmed = { id: "j2", status: "confirmed", booking: null } as never;
    expect(customerNextStep([confirmed, draft], []).to).toBe("/customer/requests/j1/details");
    expect(customerNextStep([confirmed], []).to).toBe("/customer/requests/j2/workers");
  });
});

describe("customer request keeps input across a language switch", () => {
  it("keeps the typed description and mode when the interface switches to Urdu", async () => {
    mockApi({ ...bootHandlers(makeUser({ role: "customer", preferred_language: "en" })), ...catalog,
      "PATCH /api/v1/auth/me/language/": jsonResponse({ preferred_language: "ur" }) });
    renderApp("/customer/requests/new", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["jobs.describe.type"] }));
    await userEvent.type(screen.getByLabelText(en["jobs.describe.textLabel"]), "Two fans in G-9");
    await userEvent.click(screen.getByRole("button", { name: en["nav.changeLanguage"].replace("{language}", "اردو") }));
    await waitFor(() => expect(document.documentElement.lang).toBe("ur"));
    expect(screen.getByLabelText(ur["jobs.describe.textLabel"])).toHaveValue("Two fans in G-9");
    expect(screen.getByRole("button", { name: ur["jobs.describe.type"] })).toHaveAttribute("aria-pressed", "true");
  });
});
