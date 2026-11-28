import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/resources/en";
import { AREAS, bootHandlers, errorEnvelope, jsonResponse, makeUser, mockApi, SERVICES, TRADES } from "../test/http";
import { renderApp } from "../test/renderApp";

/** Request & chat → Quote → Work progress, shown on all three screens. */
const stages = () => screen.getByRole("navigation", { name: en["stage.label"] });

const BASE = "/api/v1/conversations/inv-1";
const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const catalog = {
  "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
  "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
  "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
};
const SHARED = {
  description: "دو چھت کے پنکھے سامان سمیت لگانے ہیں۔",
  trade: "electrician", services: ["elec_fan_install"], services_excluded: [], city: "islamabad", area: "isb-g-9",
  window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z", budget_preference_pkr: "3500.00", has_photos: false,
};
const header = (role: "customer" | "worker", status = "active") => ({
  invitation: { id: "inv-1", status, created_at: "2030-01-01T10:00:00Z", closed_at: status === "active" ? null : "2030-01-02T10:00:00Z" },
  role, can_write: status === "active", job: SHARED, job_id: role === "customer" ? "job-1" : null, booking: null, write_blocked_reason: status === "active" ? null : "closed", contact_block: { blocked: false, by_me: false, block_id: null },
  counterpart: role === "customer" ? { role: "worker", worker_id: "00000000-0000-4000-8000-00000000a7f3", trade: "electrician" } : { role: "customer" },
});
const message = (id: string, overrides: Record<string, unknown> = {}) => ({
  id, client_id: null, sender_role: "worker", mine: false, kind: "text", text: "Salaam, I can come tomorrow.", caption_status: null,
  interpreted_text: null, audio_url: null, duration_seconds: null, created_at: "2030-01-01T10:05:00Z", ...overrides,
});
const finding = (overrides: Record<string, unknown> = {}) => ({
  id: "f-1", source: "ai", code: "materials_responsibility", blocking: true,
  question: "The customer expects materials to be included, but the quote does not include them. Who supplies and pays for the materials?",
  ask: "worker",
  sources: [
    { kind: "request", ref: "description", text: "دو چھت کے پنکھے سامان سمیت لگانے ہیں۔" },
    { kind: "quote", ref: "materials", text: "customer" },
  ],
  status: "open", resolution: null, resolution_note: null, resolved_role: null, resolved_at: null, ...overrides,
});
const quote = (overrides: Record<string, unknown> = {}) => ({
  id: "q-1", version: 1, status: "submitted", timezone: "Asia/Karachi",
  inspection_only: false, scope: "Install two ceiling fans", quantity: 2, labour_amount: "600.00", labour_basis: "per_item",
  materials: "customer", materials_amount: null, visit_fee: null, visit_fee_treatment: "none", exclusions: "",
  start_at: "2030-01-10T12:00:00Z", end_at: "2030-01-10T14:00:00Z",
  totals: { labour_total: "1200.00", materials_total: null, visit_total: null, known_total: "1200.00", unknown: [], complete: true },
  submitted_at: "2030-01-01T11:00:00Z", superseded_at: null, expires_at: "2030-01-02T11:00:00Z", expired: false,
  check: { status: "findings", provider: "fixture", simulated: true, checked_at: "2030-01-01T11:00:01Z", started_at: null, failure: null },
  manual_review_at: null, findings: [finding()], issues: {}, ...overrides,
});
const readiness = (ready: boolean, blocking: string[] = []) => ({
  invitation_id: "inv-1", quote_id: "q-1", version: 1, expires_at: "2030-01-02T11:00:00Z", ready, blocking, warnings: [], booking_id: null,
});
const listing = (current: unknown = null, ready = false, blocking: string[] = ["no_quote"], history: unknown[] = []) => ({
  current, draft: null, history, readiness: readiness(ready, blocking),
});
const customer = () => makeUser({ role: "customer", preferred_language: "en" });
const worker = () => makeUser({ role: "worker", preferred_language: "en" });

describe("conversation messages", () => {
  it("retrying a failed send reuses the same send ID and shows the message once", async () => {
    let attempts = 0;
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing()),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [message("m-1")], has_more_before: false }),
      [`POST ${BASE}/messages/`]: (init) => {
        attempts += 1;
        if (attempts === 1) return jsonResponse(errorEnvelope("server_error", "r1"), 500);
        const body = JSON.parse(String(init.body)) as { client_id: string; text: string };
        return jsonResponse(message("m-2", { mine: true, sender_role: "customer", client_id: body.client_id, text: body.text }), 201);
      },
    });
    renderApp("/conversations/inv-1", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["conv.title"] })).toBeInTheDocument();
    expect(screen.getByText("With: Electrician · ref. A7F3")).toBeInTheDocument();
    expect(await screen.findByText("Salaam, I can come tomorrow.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(en["conv.messageLabel"]), "Please bring a ladder.");
    await userEvent.click(screen.getByRole("button", { name: en["conv.send"] }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText(en["conv.messageLabel"])).toHaveValue("Please bring a ladder."); // nothing typed is lost
    await userEvent.click(screen.getByRole("button", { name: en["conv.send"] }));
    expect(await screen.findByText("Please bring a ladder.")).toBeInTheDocument();

    const sends = calls.filter((call) => call.method === "POST" && call.path === `${BASE}/messages/`);
    expect(sends).toHaveLength(2);
    expect((sends[0]!.body as { client_id: string }).client_id).toBe((sends[1]!.body as { client_id: string }).client_id);
    expect(screen.getAllByText("Please bring a ladder.")).toHaveLength(1);
    expect(screen.getByLabelText(en["conv.messageLabel"])).toHaveValue("");
  }, 15000);

  it("a voice note is sent with the caption the sender approved", async () => {
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("worker")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing()),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [], has_more_before: false }),
      "POST /api/v1/audio/clips/": jsonResponse({ id: "clip-9", purpose: "message", source: "upload", mime_type: "audio/wav", size_bytes: 100, duration_seconds: 2, created_at: "x", content_url: "/api/v1/audio/clips/clip-9/content/" }, 201),
      "POST /api/v1/audio/transcribe/": jsonResponse({ id: "tr-9", clip_id: "clip-9", text: "میں کل شام آ سکتا ہوں", language: "ur", language_hint: "en", no_speech: false, provider: "fixture", model: "fixture-stt-v1", simulated: true, reused: false }),
      [`POST ${BASE}/messages/`]: (init) => {
        const body = JSON.parse(String(init.body)) as { client_id: string; text: string };
        return jsonResponse(message("m-3", { mine: true, sender_role: "worker", kind: "voice", client_id: body.client_id, text: body.text, caption_status: "approved", audio_url: `${BASE}/messages/m-3/audio/`, duration_seconds: 2 }), 201);
      },
    });
    renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText(en["conv.empty"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["conv.voice"] }));
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File([new Uint8Array(2048)], "note.wav", { type: "audio/wav" }));
    await userEvent.click(await screen.findByRole("button", { name: en["conv.prepareCaption"] }, { timeout: 5000 })); // jsdom: duration probe times out
    const caption = await screen.findByLabelText(en["conv.captionLabel"]);
    expect(caption).toHaveValue("میں کل شام آ سکتا ہوں");
    await userEvent.type(caption, "، پانچ بجے");
    await userEvent.click(screen.getByRole("button", { name: en["conv.send"] }));
    expect(await screen.findByText("میں کل شام آ سکتا ہوں، پانچ بجے")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["conv.playVoice"] })).toBeInTheDocument();

    const upload = calls.find((call) => call.path === "/api/v1/audio/clips/")!;
    expect((upload.body as FormData).get("purpose")).toBe("message");
    const send = calls.find((call) => call.method === "POST" && call.path === `${BASE}/messages/`)!;
    expect(send.body).toMatchObject({ kind: "voice", audio_clip_id: "clip-9", transcription_id: "tr-9", text: "میں کل شام آ سکتا ہوں، پانچ بجے" });
  }, 15000);

  it("a closed invitation keeps the history readable but offers no composer", async () => {
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer", "withdrawn")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing(quote({ findings: [] }), false, ["invitation_not_active"])),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [message("m-1"), message("m-2", { kind: "voice", text: "", caption_status: "unavailable", audio_url: `${BASE}/messages/m-2/audio/` })], has_more_before: false }),
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText(en["conv.closedBody"])).toBeInTheDocument();
    expect(await screen.findByText("Salaam, I can come tomorrow.")).toBeInTheDocument();
    expect(screen.getAllByText(en["conv.captionUnavailable"]).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(en["conv.messageLabel"])).not.toBeInTheDocument();
    expect(within(stages()).getByText(en["stage.chat.closed"])).toBeInTheDocument();
    // The quote stays readable on its own screen, with the reason it cannot be accepted.
    await userEvent.click(await screen.findByRole("link", { name: en["quote.view"] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/conversations/inv-1/quote"));
    expect(await screen.findByText(en["quote.blocking.invitation_not_active"])).toBeInTheDocument();
    expect(screen.queryByText(en["quote.ready.title"])).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["accept.open"] })).not.toBeInTheDocument();
  });
});

describe("job stages: request & chat → quote → work progress", () => {
  it("customer: one short waiting status before a quote, and no quote panel on the chat screen", async () => {
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing()),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [], has_more_before: false }),
    });
    renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText(en["quote.waiting"])).toBeInTheDocument();
    const nav = within(stages());
    expect(nav.getByText(en["stage.chat"]).closest("[aria-current]")).toHaveAttribute("aria-current", "step");
    expect(nav.getByText(en["stage.quote.none"])).toBeInTheDocument();
    expect(nav.getByText(en["stage.work.none"])).toBeInTheDocument();
    expect(nav.queryByRole("link", { name: new RegExp(en["stage.work"]) })).not.toBeInTheDocument(); // nothing booked yet
    expect(nav.getByRole("link", { name: new RegExp(en["stage.quote"]) })).toHaveAttribute("href", "/conversations/inv-1/quote");
    // No quote form, terms, check panel or acceptance on the chat screen.
    expect(screen.queryByRole("button", { name: en["accept.open"] })).not.toBeInTheDocument();
    expect(screen.queryByText(en["quote.check.label"], { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["quote.form.submit"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: en["quote.view"] })).not.toBeInTheDocument();
    // The compact request summary keeps the full request one tap away.
    expect(screen.getByText(en["conv.viewRequest"])).toBeInTheDocument();
  });

  it("customer: View quote opens the quote screen (no chat thread there) without reloading the invitation; Back returns to chat with the unsent message", async () => {
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing(quote(), false, ["unresolved_findings"])),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [message("m-1")], has_more_before: false }),
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText("Salaam, I can come tomorrow.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(en["conv.messageLabel"]), "Is the ladder included?");
    const view = await screen.findByRole("link", { name: en["quote.view"] });
    expect(screen.getByText(en["quote.summary.blocked"])).toBeInTheDocument();
    await userEvent.click(view);

    await waitFor(() => expect(router.state.location.pathname).toBe("/conversations/inv-1/quote"));
    expect(await screen.findByRole("heading", { level: 1, name: en["quote.title"] })).toBeInTheDocument();
    // Total, materials, scope and appointment first.
    const terms = within(screen.getByRole("region", { name: en["quote.versionLabel"].replace("{version}", "1") }));
    expect(terms.getAllByText("PKR 1,200")[0]).toHaveAttribute("dir", "ltr");
    expect(terms.getByText(en["quote.materials.customer"])).toBeInTheDocument();
    expect(terms.getByText("Install two ceiling fans")).toBeInTheDocument();
    // The blocking issue sits with the next action; the sources can be inspected.
    const next = within(screen.getByRole("complementary", { name: en["quote.nextAction"] }));
    expect(next.getByText(en["quote.notReady.title"])).toBeInTheDocument();
    expect(next.getByText(en["quote.finding.code.materials_responsibility"])).toBeInTheDocument();
    expect(next.getByText(en["quote.finding.showSources"].replace("{count}", "2"))).toBeInTheDocument();
    expect(next.getByRole("link", { name: en["quote.backToChat"] })).toHaveAttribute("href", "/conversations/inv-1");
    // No chat thread or composer on the quote screen.
    expect(screen.queryByRole("heading", { name: en["conv.messages"] })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(en["conv.messageLabel"])).not.toBeInTheDocument();
    expect(calls.filter((call) => call.path === `${BASE}/`)).toHaveLength(1); // the layout stayed mounted

    await act(() => router.navigate(-1));
    await waitFor(() => expect(router.state.location.pathname).toBe("/conversations/inv-1"));
    expect(await screen.findByLabelText(en["conv.messageLabel"])).toHaveValue("Is the ladder included?");
  });

  it("a direct link to the quote screen works on its own (refresh), and fetches no messages", async () => {
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing(quote({ findings: [] }), true, [])),
    });
    renderApp("/conversations/inv-1/quote", "en");
    expect(await screen.findByText(en["quote.ready.title"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["accept.open"] })).toBeInTheDocument();
    expect(within(stages()).getByText(en["stage.quote.ready"].replace("{version}", "1"))).toBeInTheDocument();
    expect(calls.some((call) => call.path.endsWith("/messages/"))).toBe(false);
  });
});

describe("quotes and agreement gaps", () => {
  it("shows the conflict with its sources, records a clarification, and is not ready meanwhile", async () => {
    let resolved = false;
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("worker")),
      [`GET ${BASE}/quotes/`]: () =>
        jsonResponse(resolved
          ? listing(quote({ check: { status: "findings", provider: "fixture", simulated: true, checked_at: "x", failure: null },
              findings: [finding({ status: "resolved", resolution: "terms_confirmed", resolution_note: "Customer buys the fans", resolved_role: "worker" })] }), true, [])
          : listing(quote(), false, ["unresolved_findings"])),
      [`POST ${BASE}/quotes/q-1/findings/f-1/resolve/`]: () => { resolved = true; return jsonResponse({ ...quote(), readiness: readiness(true) }); },
    });
    renderApp("/conversations/inv-1/quote", "en");
    expect(await screen.findByText(en["quote.notReady.title"])).toBeInTheDocument();
    expect(screen.getByText(en["quote.blocking.unresolved_findings"])).toBeInTheDocument();
    expect(screen.getByText(en["quote.finding.code.materials_responsibility"])).toBeInTheDocument();
    expect(screen.getByText(/Who supplies and pays for the materials\?/)).toBeInTheDocument();
    expect(screen.getByText("“دو چھت کے پنکھے سامان سمیت لگانے ہیں۔”")).toBeInTheDocument(); // the source statement
    expect(screen.getByText(`“${en["quote.materials.customer"]}”`)).toBeInTheDocument();
    expect(screen.getByText(en["voice.simulated"])).toBeInTheDocument(); // fixture check is labelled simulated
    expect(screen.getByText("PKR 600 per item × 2 = PKR 1,200")).toBeInTheDocument(); // full terms, behind "View full terms"
    expect(screen.getByRole("button", { name: en["quote.revise"] })).toBeInTheDocument(); // the worker can revise instead

    const save = screen.getByRole("button", { name: en["quote.resolution.save"] });
    expect(save).toBeDisabled(); // a clarification needs a note
    await userEvent.type(screen.getByLabelText(new RegExp(en["quote.resolution.noteLabel"].replace(/[()]/g, "\\$&"))), "Customer buys the fans");
    await userEvent.click(save);
    expect(await screen.findByText(en["quote.ready.title"])).toBeInTheDocument();
    expect(screen.getByText(en["quote.settled"].replace("{count}", "1"))).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/resolve/"))?.body).toEqual({ resolution: "terms_confirmed", note: "Customer buys the fans" });
  });

  it("an automatic check that could not run is never shown as passed; the customer can review manually", async () => {
    let reviewed = false;
    const unavailable = () => quote({
      findings: [], manual_review_at: reviewed ? "2030-01-01T12:00:00Z" : null,
      check: { status: "unavailable", provider: "gemini", simulated: false, checked_at: "x", failure: "ai_provider_unavailable" },
    });
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("customer")),
      [`GET ${BASE}/quotes/`]: () => jsonResponse(listing(unavailable(), reviewed, reviewed ? [] : ["automated_check_unavailable"])),
      [`POST ${BASE}/quotes/q-1/manual-review/`]: () => { reviewed = true; return jsonResponse({ ...unavailable(), readiness: readiness(true) }); },
    });
    renderApp("/conversations/inv-1/quote", "en");
    expect(await screen.findByText(en["quote.check.unavailableTitle"])).toBeInTheDocument();
    expect(screen.getByText(en["quote.blocking.automated_check_unavailable"])).toBeInTheDocument();
    expect(screen.queryByText(en["quote.check.passed"])).not.toBeInTheDocument();
    expect(screen.queryByText(en["quote.ready.title"])).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["quote.check.retry"] })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["quote.check.manualReview"] }));
    expect(await screen.findByText(en["quote.ready.title"])).toBeInTheDocument();
    expect(screen.getByText(en["quote.check.manualDone"])).toBeInTheDocument();
    expect(calls.some((call) => call.path.endsWith("/manual-review/"))).toBe(true);
  });

  it("worker: Prepare quote opens the quote screen with the form; sending returns to the quote view", async () => {
    let submitted = false;
    const calls = mockApi({
      ...bootHandlers(worker()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("worker")),
      [`GET ${BASE}/quotes/`]: () => jsonResponse(submitted
        ? listing(quote({ materials: "worker_extra", findings: [], check: { status: "passed", provider: "fixture", simulated: true, checked_at: "x", failure: null } }), true, [])
        : listing()),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [], has_more_before: false }),
      [`PUT ${BASE}/quotes/draft/`]: (init) => jsonResponse({ ...quote({ status: "draft", version: null, findings: [], check: { status: "not_run", provider: null, simulated: false, checked_at: null, failure: null } }), ...JSON.parse(String(init.body)) }),
      [`POST ${BASE}/quotes/draft/submit/`]: () => { submitted = true; return jsonResponse(quote()); },
    });
    const { router } = renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText(en["conv.empty"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["quote.form.submit"] })).not.toBeInTheDocument(); // never on the chat screen
    await userEvent.click(await screen.findByRole("link", { name: en["quote.create"] }));
    await waitFor(() => expect(router.state.location.search).toBe("?edit=1"));
    expect(router.state.location.pathname).toBe("/conversations/inv-1/quote");
    // The customer's request stays beside the form.
    expect(screen.getByRole("complementary", { name: en["quote.requestAside"] })).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(en["quote.field.scope"]), "Install two ceiling fans");
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["quote.basis.per_item"]) }));
    await userEvent.type(screen.getByLabelText(en["quote.form.labourAmount"]), "600");
    await userEvent.type(screen.getByLabelText(en["quote.field.quantity"]), "2");
    await userEvent.click(screen.getByRole("radio", { name: new RegExp(en["quote.materials.worker_extra"]) }));
    await userEvent.type(screen.getByLabelText(en["jobs.field.date"]), "2030-01-10");
    await userEvent.type(screen.getByLabelText(en["jobs.field.startTime"]), "17:00");
    await userEvent.type(screen.getByLabelText(en["jobs.field.endTime"]), "19:00");
    await userEvent.click(screen.getByRole("button", { name: en["quote.form.submit"] }));
    expect(await screen.findByText(en["quote.ready.title"], undefined, { timeout: 10000 })).toBeInTheDocument(); // save, submit, reload

    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.body).toMatchObject({
      inspection_only: false, scope: "Install two ceiling fans", quantity: 2, labour_amount: "600", labour_basis: "per_item",
      materials: "worker_extra", materials_amount: null, visit_fee: null, visit_fee_treatment: "none",
      start_at: "2030-01-10T17:00:00+05:00", end_at: "2030-01-10T19:00:00+05:00", // Asia/Karachi wall time
    });
    expect(calls.some((call) => call.path === `${BASE}/quotes/draft/submit/`)).toBe(true);
    await waitFor(() => expect(screen.queryByRole("button", { name: en["quote.form.submit"] })).not.toBeInTheDocument());
    expect(router.state.location.search).toBe("");
    expect(screen.getByRole("button", { name: en["quote.revise"] })).toBeInTheDocument();
  }, 30000);

  it("worker: typed quote terms survive a visit to the chat", async () => {
    mockApi({
      ...bootHandlers(worker()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(header("worker")),
      [`GET ${BASE}/quotes/`]: jsonResponse(listing()),
      [`GET ${BASE}/messages/`]: jsonResponse({ results: [], has_more_before: false }),
    });
    const { router } = renderApp("/conversations/inv-1/quote?edit=1", "en");
    await userEvent.type(await screen.findByLabelText(en["quote.field.scope"]), "Fix the wiring");
    await userEvent.click(screen.getByRole("link", { name: en["quote.backToChat"] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/conversations/inv-1"));
    await userEvent.click(await screen.findByRole("link", { name: en["quote.continueDraft"] }));
    expect(await screen.findByLabelText(en["quote.field.scope"])).toHaveValue("Fix the wiring");
  });

  it("a third account gets the not-found page", async () => {
    mockApi({
      ...bootHandlers(customer()), ...catalog,
      [`GET ${BASE}/`]: jsonResponse(errorEnvelope("not_found", "r1"), 404),
      [`GET ${BASE}/quotes/`]: jsonResponse(errorEnvelope("not_found", "r2"), 404),
    });
    renderApp("/conversations/inv-1", "en");
    expect(await screen.findByText(en["errors.not_found"])).toBeInTheDocument();
    expect(screen.queryByText(en["conv.messages"])).not.toBeInTheDocument();
  });
});
