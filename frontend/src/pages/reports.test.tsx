import { screen, waitFor } from "@testing-library/react";
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
type Block = { blocked: boolean; by_me: boolean; block_id: string | null };
const NO_BLOCK: Block = { blocked: false, by_me: false, block_id: null };
const header = (block: Block = NO_BLOCK) => ({
  invitation: { id: "inv-1", status: "active", created_at: "x", closed_at: null }, role: "worker", can_write: !block.blocked,
  write_blocked_reason: block.blocked ? "contact_blocked" : null, contact_block: block, job: SHARED, job_id: null, booking: null,
  counterpart: { role: "customer" },
});
const conversation = (block: Block = NO_BLOCK) => ({
  "GET /api/v1/conversations/inv-1/": jsonResponse(header(block)),
  "GET /api/v1/conversations/inv-1/quotes/": jsonResponse({ current: null, draft: null, history: [],
    readiness: { invitation_id: "inv-1", quote_id: null, version: null, expires_at: null, ready: false, blocking: ["no_quote"], warnings: [], booking_id: null } }),
  "GET /api/v1/conversations/inv-1/messages/": jsonResponse({ results: [], has_more_before: false }),
});
const report = (overrides: Record<string, unknown> = {}) => ({
  id: "r-1", status: "open", category: "harassment", reporter_role: "worker", interaction: { invitation_id: "inv-1", booking_id: null },
  awaiting_reply: false, created_at: "2030-01-01T10:00:00Z", updated_at: "x", closed_at: null, description: "Abusive messages",
  evidence: [], messages: [] as { from: string; text: string; at: string }[], can_reply: true, can_add_evidence: true, ...overrides,
});
const worker = (overrides: Record<string, unknown> = {}) => makeUser({ role: "worker", preferred_language: "en", ...overrides });

describe("reporting a concern", () => {
  it("files a private report from the conversation without choosing who is reported", async () => {
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog, ...conversation(),
      "POST /api/v1/reports/": jsonResponse({ ...report(), created: true }, 201),
      "GET /api/v1/reports/r-1/": jsonResponse(report()),
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    await userEvent.click(await screen.findByRole("link", { name: en["safety.report"] }));
    expect(router.state.location.search).toBe("?invitation=inv-1");
    expect(await screen.findByText(en["report.new.privateBody"])).toBeInTheDocument();
    const send = screen.getByRole("button", { name: en["report.submit"] });
    expect(send).toBeDisabled(); // a category and a description or voice note are needed
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["report.category.harassment"]) }));
    await userEvent.type(screen.getByLabelText(en["report.descriptionLabel"]), "Abusive messages");
    await userEvent.click(send);
    await waitFor(() => expect(router.state.location.pathname).toBe("/reports/r-1"));
    const body = calls.find((call) => call.method === "POST" && call.path === "/api/v1/reports/")!.body as Record<string, unknown>;
    expect(body).toMatchObject({ invitation_id: "inv-1", category: "harassment", description: "Abusive messages" });
    expect(Object.keys(body).sort()).toEqual(["category", "client_id", "description", "invitation_id"]); // no reported account
    expect(await screen.findByText(en["report.statusExplain.open"])).toBeInTheDocument();
  });

  it("shows the staff message meant for the reporter and sends a reply", async () => {
    let current = report({ status: "reviewing", awaiting_reply: true, messages: [{ from: "staff", text: "When did it happen?", at: "2030-01-02T10:00:00Z" }] });
    const calls = mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/reports/r-1/": () => jsonResponse(current),
      "POST /api/v1/reports/r-1/replies/": (init) => {
        const { text } = JSON.parse(String(init.body)) as { text: string };
        current = { ...current, awaiting_reply: false, messages: [...current.messages, { from: "you", text, at: "2030-01-02T11:00:00Z" }] };
        return jsonResponse(current, 201);
      },
    });
    renderApp("/reports/r-1", "en");
    expect(await screen.findByText(en["report.needsReply"])).toBeInTheDocument();
    expect(screen.getByText("When did it happen?")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(en["report.replyLabel"]), "Last Tuesday evening");
    await userEvent.click(screen.getByRole("button", { name: en["report.sendReply"] }));
    expect(await screen.findByText("Last Tuesday evening")).toBeInTheDocument();
    expect(screen.queryByText(en["report.needsReply"])).not.toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/replies/"))?.body).toEqual({ text: "Last Tuesday evening" });
  });

  it("someone else's report is not found", async () => {
    mockApi({ ...bootHandlers(worker()), "GET /api/v1/reports/r-9/": jsonResponse(errorEnvelope("not_found", "r1"), 404) });
    renderApp("/reports/r-9", "en");
    expect(await screen.findByText(en["errors.not_found"])).toBeInTheDocument();
  });
});

describe("blocking contact", () => {
  it("blocks after confirmation and then explains why messages are closed", async () => {
    let block: Block = NO_BLOCK;
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      "GET /api/v1/conversations/inv-1/": () => jsonResponse(header(block)),
      "GET /api/v1/conversations/inv-1/quotes/": conversation()["GET /api/v1/conversations/inv-1/quotes/"],
      "GET /api/v1/conversations/inv-1/messages/": conversation()["GET /api/v1/conversations/inv-1/messages/"],
      "POST /api/v1/blocks/": () => { block = { blocked: true, by_me: true, block_id: "b-1" }; return jsonResponse({ id: "b-1", created_at: "x" }, 201); },
    });
    renderApp("/conversations/inv-1", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["safety.block"] }));
    expect(screen.getByText(en["safety.blockExplain"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["safety.blockConfirm"] }));
    expect(await screen.findByText(en["safety.blockedByMe"])).toBeInTheDocument();
    expect(screen.getByText(en["conv.blockedBody"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["safety.unblock"] })).toBeInTheDocument();
    expect(calls.find((call) => call.path === "/api/v1/blocks/")?.body).toEqual({ invitation_id: "inv-1" });
  });
});

describe("restricted account", () => {
  it("the dashboard explains what a restricted account can still do", async () => {
    mockApi({
      ...bootHandlers(makeUser({ role: "customer", preferred_language: "en", restricted: true })), ...catalog,
      "GET /api/v1/jobs/": jsonResponse(page([])),
      "GET /api/v1/bookings/": jsonResponse(page([])),
    });
    renderApp("/customer", "en");
    expect(await screen.findByText(en["restricted.title"])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["report.mine"] })).toBeInTheDocument();
  });
});
