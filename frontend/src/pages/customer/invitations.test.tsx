import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../../i18n/resources/en";
import { AREAS, bootHandlers, errorEnvelope, jsonResponse, makeDashboard, makeUser, mockApi, SERVICES, TRADES, workerHandlers } from "../../test/http";
import { renderApp } from "../../test/renderApp";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const catalog = {
  "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
  "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
  "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
};
const SHARED = {
  description: "Two ceiling fans. Call me on 0300 1234567",
  trade: "electrician", services: ["elec_fan_install"], services_excluded: [], city: "islamabad", area: "isb-g-9",
  window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z", budget_preference_pkr: "3500.00", has_photos: true,
};
const card = (id: string, speciality = true) => ({
  worker_id: id, display_label: null, trade: "electrician", services_matched: ["elec_fan_install"],
  specialities_matched: speciality ? ["elec_fan_install"] : [], serves_selected_area: true,
  verification: { status: "demo_approved", simulated: true }, is_new: true, previous_invitation: null,
  reasons: speciality
    ? [{ code: "speciality", services: ["elec_fan_install"] }, { code: "serves_area", area: "isb-g-9" }]
    : [{ code: "offers", services: ["elec_fan_install"] }, { code: "serves_area", area: "isb-g-9" }],
});
const recs = (workers: unknown[], active: unknown = null) => ({
  request: { trade: "electrician", services: ["elec_fan_install"], city: "islamabad", area: "isb-g-9", window_start: SHARED.window_start, window_end: SHARED.window_end },
  shared_preview: SHARED, privacy_warnings: ["phone_number"], workers, active_invitation: active,
});
const invitation = (status = "active") => ({
  id: "inv-1", status, worker: { worker_id: "00000000-0000-4000-8000-00000000a7f3", display_label: null, trade: "electrician" },
  created_at: "x", seen_at: null, closed_at: null, decline_reason: null,
});
const customer = () => makeUser({ role: "customer", preferred_language: "en" });

describe("find a worker (customer)", () => {
  it("shows matching workers with reasons and an honest empty state", async () => {
    mockApi({ ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/jobs/job-1/recommendations/": jsonResponse(recs([card("00000000-0000-4000-8000-00000000a7f3"), card("00000000-0000-4000-8000-0000000000b2", false)])),
      "GET /api/v1/jobs/job-1/invitations/": jsonResponse({ results: [] }) });
    renderApp("/customer/requests/job-1/workers", "en");
    expect(await screen.findByText(en["rec.list.heading"].replace("{count}", "2"))).toBeInTheDocument();
    expect(screen.getByText("Electrician · ref. A7F3")).toBeInTheDocument();
    expect(screen.getByText("Listed speciality: Ceiling fan installation")).toBeInTheDocument();
    expect(screen.getByText("Offers: Ceiling fan installation")).toBeInTheDocument();
    expect(screen.getAllByText("Serves your selected area (G-9)")).toHaveLength(2);
    expect(screen.getAllByText(en["rec.verification.demo_approved"])).toHaveLength(2);
    expect(screen.getByText(/5:00\s?pm – 7:00\s?pm/i)).toBeInTheDocument(); // requested window in Asia/Karachi
  });

  it("explains when nobody matches", async () => {
    mockApi({ ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/jobs/job-1/recommendations/": jsonResponse(recs([])),
      "GET /api/v1/jobs/job-1/invitations/": jsonResponse({ results: [] }) });
    renderApp("/customer/requests/job-1/workers", "en");
    expect(await screen.findByText(en["rec.empty.title"])).toBeInTheDocument();
    expect(screen.getByText(en["rec.empty.body"].replace("{services}", "Ceiling fan installation").replace("{area}", "G-9"))).toBeInTheDocument();
  });

  it("previews exactly what is shared, sends, then withdraws", async () => {
    let active: unknown = null;
    const calls = mockApi({ ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/jobs/job-1/recommendations/": () => jsonResponse(recs([card("00000000-0000-4000-8000-00000000a7f3")], active)),
      "GET /api/v1/jobs/job-1/invitations/": () => jsonResponse({ results: active ? [active] : [] }),
      "POST /api/v1/jobs/job-1/invitations/": () => { active = invitation(); return jsonResponse({ ...invitation(), created: true }, 201); },
      "POST /api/v1/jobs/job-1/invitations/inv-1/withdraw/": () => { active = null; return jsonResponse(invitation("withdrawn")); },
    });
    renderApp("/customer/requests/job-1/workers", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["rec.invite"] }));
    const preview = screen.getByRole("region", { name: en["rec.preview.title"] });
    expect(within(preview).getAllByText(SHARED.description)).toHaveLength(2); // shared view + editable box
    expect(within(preview).getByText(en["rec.preview.notShared.body"])).toBeInTheDocument();
    expect(within(preview).getByText(en["rec.preview.warning.phone"])).toBeInTheDocument();
    await userEvent.click(within(preview).getByRole("button", { name: en["rec.preview.send"] }));
    expect(await screen.findByText(en["rec.active.title"])).toBeInTheDocument();
    expect(calls.find((call) => call.method === "POST" && call.path.endsWith("/invitations/"))?.body).toEqual({ worker_id: "00000000-0000-4000-8000-00000000a7f3" });
    expect(screen.queryByRole("button", { name: en["rec.invite"] })).not.toBeInTheDocument(); // one active at a time
    await userEvent.click(screen.getByRole("button", { name: en["rec.active.withdraw"] }));
    await waitFor(() => expect(screen.queryByText(en["rec.active.title"])).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: en["rec.invite"] })).toBeInTheDocument();
  }, 15000);

  it("shows the conflict when another invitation is already active", async () => {
    mockApi({ ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/jobs/job-1/recommendations/": jsonResponse(recs([card("00000000-0000-4000-8000-00000000a7f3")])),
      "GET /api/v1/jobs/job-1/invitations/": jsonResponse({ results: [] }),
      "POST /api/v1/jobs/job-1/invitations/": jsonResponse(errorEnvelope("invitation_already_active", "r1", { invitation_id: "inv-9" }), 409) });
    renderApp("/customer/requests/job-1/workers", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["rec.invite"] }));
    await userEvent.click(screen.getByRole("button", { name: en["rec.preview.send"] }));
    expect(await screen.findByText(en["errors.invitation_already_active"])).toBeInTheDocument();
  });
});

describe("job invitations (worker)", () => {
  it("lists my invitations on the dashboard, shows shared details and declines with a reason", async () => {
    const workerInvitation = (status: string, reason: string | null = null) => ({
      id: "inv-1", status, created_at: "x", seen_at: "x", closed_at: status === "active" ? null : "x", decline_reason: reason, job: SHARED,
    });
    const calls = mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      ...workerHandlers(makeDashboard(null)),
      "GET /api/v1/invitations/": jsonResponse(page([workerInvitation("active")])),
      "GET /api/v1/invitations/inv-1/": jsonResponse(workerInvitation("active")),
      "POST /api/v1/invitations/inv-1/decline/": jsonResponse(workerInvitation("declined", "too_far")),
    });
    const { router } = renderApp("/worker", "en");
    expect(await screen.findByText(en["inv.inbox.heading"])).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("link", { name: en["jobs.list.open"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["inv.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker/invitations/inv-1");
    expect(screen.getByText(en["inv.activeNote"])).toBeInTheDocument();
    expect(screen.getByText(en["inv.privacyNote"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["inv.reason.too_far"]) }));
    await userEvent.click(screen.getByRole("button", { name: en["inv.decline.button"] }));
    expect(await screen.findByText(en["inv.declinedNote"])).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/decline/"))?.body).toEqual({ reason: "too_far" });
  }, 15000);
});
