import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../../i18n/resources/en";
import { AREAS, bootHandlers, errorEnvelope, jsonResponse, makeUser, mockApi, SERVICES, TRADES } from "../../test/http";
import { renderApp } from "../../test/renderApp";

const customer = () => makeUser({ role: "customer", preferred_language: "en" });
const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const catalog = {
  "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
  "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
  "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
};

function makeJob(overrides: Record<string, unknown> = {}, details: Record<string, unknown> = {}) {
  return {
    id: "job-1", status: "draft", created_at: "x", updated_at: "x", confirmed_at: null,
    source: { kind: "text", language: "en", original_text: "Two fans in G-9, not the UPS, tomorrow evening", audio_clip_id: null, transcription_id: null },
    details: {
      description: "Two fans in G-9", trade: "electrician", services: ["elec_fan_install"], services_excluded: [],
      city: "islamabad", area: "isb-g-9", preferred_time_text: "kal shaam", window_start: null, window_end: null,
      timezone: "Asia/Karachi", address_private: "", access_notes: "", budget_pkr: null, ...details,
    },
    suggestions: { interpretation_id: "i1", provider: "fixture", simulated: true, fields: {}, missing: [], uncertain: ["preferred_time_text"], unmatched_mentions: [], heard: {} },
    photos: [], issues: { window_start: ["required"], window_end: ["required"] }, ready_to_confirm: false,
    ...overrides,
  };
}

describe("customer dashboard", () => {
  it("offers 'Describe your job' and lists drafts and confirmed requests", async () => {
    mockApi({
      ...bootHandlers(customer()),
      ...catalog,
      "GET /api/v1/jobs/": jsonResponse(page([
        { id: "d1", status: "draft", description: "Leaking tap", trade: null, services: [], city: null, area: null, window_start: null, window_end: null, updated_at: "x", confirmed_at: null },
        { id: "c1", status: "confirmed", description: "Two fans", trade: "electrician", services: ["elec_fan_install"], city: "islamabad", area: "isb-g-9", window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z", updated_at: "x", confirmed_at: "x" },
      ])),
    });
    renderApp("/customer", "en");
    expect(await screen.findByRole("link", { name: en["jobs.describe.cta"] })).toHaveAttribute("href", "/customer/requests/new");
    expect(await screen.findByText("Electrician: Ceiling fan installation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["jobs.list.continue"] })).toHaveAttribute("href", "/customer/requests/d1/details");
    expect(screen.getByRole("link", { name: en["jobs.list.open"] })).toHaveAttribute("href", "/customer/requests/c1");
    expect(screen.getByText(/5:00\s?pm – 7:00\s?pm/i)).toBeInTheDocument(); // 12:00Z shown as Asia/Karachi
    expect(screen.getByRole("link", { name: en["home.managePhone"] })).toBeInTheDocument();
  });
});

describe("job request flow", () => {
  it("types a request, chooses the exact time for 'kal shaam', reviews and confirms", async () => {
    let stored: Record<string, unknown> = makeJob();
    const calls = mockApi({
      ...bootHandlers(customer()),
      ...catalog,
      "POST /api/v1/jobs/": jsonResponse(makeJob({ suggestions: null }, { trade: null, services: [], area: null, city: null, preferred_time_text: "" }), 201),
      "POST /api/v1/interpretations/": jsonResponse({ id: "i1" }, 201),
      "POST /api/v1/jobs/job-1/source/": () => jsonResponse(stored),
      "GET /api/v1/jobs/job-1/": () => jsonResponse(stored),
      "PATCH /api/v1/jobs/job-1/": () => {
        stored = makeJob({ issues: {}, ready_to_confirm: true }, { window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z" });
        return jsonResponse(stored);
      },
      "POST /api/v1/jobs/job-1/confirm/": () => {
        stored = { ...stored, status: "confirmed", confirmed_at: "2030-01-01T10:00:00Z", issues: {}, ready_to_confirm: false };
        return jsonResponse({ ...stored, already_confirmed: false });
      },
    });
    const { router } = renderApp("/customer/requests/new", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["jobs.describe.type"] }));
    await userEvent.type(screen.getByLabelText(en["jobs.describe.textLabel"]), "Two fans in G-9, not the UPS, tomorrow evening");
    await userEvent.click(screen.getByRole("button", { name: en["jobs.describe.continue"] }));

    expect(await screen.findByRole("heading", { level: 1, name: en["jobs.details.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/customer/requests/job-1/details");
    expect(screen.getByText(en["jobs.time.youSaid"].replace("{phrase}", "kal shaam"))).toBeInTheDocument();
    expect(screen.getByText(en["jobs.time.choosePrompt"])).toBeInTheDocument();
    expect(screen.getByText("Two fans in G-9, not the UPS, tomorrow evening")).toBeInTheDocument(); // original kept
    fireEvent.change(screen.getByLabelText(en["jobs.field.date"]), { target: { value: "2030-01-10" } });
    fireEvent.change(screen.getByLabelText(en["jobs.field.startTime"]), { target: { value: "17:00" } });
    fireEvent.change(screen.getByLabelText(en["jobs.field.endTime"]), { target: { value: "19:00" } });
    await userEvent.click(screen.getByRole("button", { name: en["jobs.details.toReview"] }));

    expect(await screen.findByRole("heading", { level: 1, name: en["jobs.review.title"] })).toBeInTheDocument();
    const patch = calls.find((call) => call.method === "PATCH")?.body as Record<string, unknown>;
    expect(patch.window_start).toBe("2030-01-10T17:00:00+05:00");
    expect(patch.window_end).toBe("2030-01-10T19:00:00+05:00");
    expect(screen.getByText(en["jobs.review.meaning"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["jobs.review.confirm"] }));
    expect(await screen.findByText(en["jobs.detail.justConfirmed"])).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/customer/requests/job-1");
    expect(calls.filter((call) => call.path === "/api/v1/jobs/").map((call) => call.body)).toEqual([
      { source_kind: "text", original_text: "Two fans in G-9, not the UPS, tomorrow evening", source_language: "en" },
    ]);
  }, 20000);

  it("keeps the draft and offers the manual path when the AI provider fails", async () => {
    mockApi({
      ...bootHandlers(customer()),
      ...catalog,
      "POST /api/v1/jobs/": jsonResponse(makeJob({ suggestions: null }, { trade: null, services: [], area: null, city: null, preferred_time_text: "" }), 201),
      "POST /api/v1/interpretations/": jsonResponse(errorEnvelope("ai_provider_unavailable", "r1", { capability: "interpretation", reason: "timeout" }), 502),
      "GET /api/v1/jobs/job-1/": jsonResponse(makeJob({ suggestions: null }, { trade: null, services: [], area: null, city: null, preferred_time_text: "" })),
    });
    const { router } = renderApp("/customer/requests/new", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["jobs.describe.type"] }));
    await userEvent.type(screen.getByLabelText(en["jobs.describe.textLabel"]), "Fix the geyser");
    await userEvent.click(screen.getByRole("button", { name: en["jobs.describe.continue"] }));
    expect(await screen.findByText(en["jobs.describe.draftKept"])).toBeInTheDocument();
    expect(screen.getByText(en["errors.ai_provider_unavailable"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["jobs.describe.continueManually"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["jobs.details.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/customer/requests/job-1/details");
  }, 15000);

  it("shows server time-window errors next to the time fields", async () => {
    mockApi({
      ...bootHandlers(customer()),
      ...catalog,
      "GET /api/v1/jobs/job-1/": jsonResponse(makeJob()),
      "PATCH /api/v1/jobs/job-1/": jsonResponse(errorEnvelope("validation_error", "r2", undefined, { window_start: [{ code: "window_in_past", message: "x" }] }), 400),
    });
    renderApp("/customer/requests/job-1/details", "en");
    fireEvent.change(await screen.findByLabelText(en["jobs.field.date"]), { target: { value: "2020-01-10" } });
    fireEvent.change(screen.getByLabelText(en["jobs.field.startTime"]), { target: { value: "17:00" } });
    fireEvent.change(screen.getByLabelText(en["jobs.field.endTime"]), { target: { value: "19:00" } });
    await userEvent.click(screen.getByRole("button", { name: en["jobs.details.saveDraft"] }));
    expect(await screen.findByText(en["fieldErrors.window_in_past"])).toBeInTheDocument();
  });

  it("reads aloud only the task, area, date and time — never the private address", async () => {
    const job = makeJob(
      { issues: {}, ready_to_confirm: true },
      { window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z", address_private: "House 5, Street 9", access_notes: "Ring twice" },
    );
    const calls = mockApi({
      ...bootHandlers(customer()),
      ...catalog,
      "GET /api/v1/jobs/job-1/": jsonResponse(job),
      "POST /api/v1/audio/synthesise/": jsonResponse(errorEnvelope("ai_provider_not_configured", "r3", { capability: "text_to_speech" }), 503),
    });
    renderApp("/customer/requests/job-1/review", "en");
    expect(await screen.findByText("House 5, Street 9")).toBeInTheDocument(); // shown privately to the owner
    await userEvent.click(screen.getByRole("button", { name: en["voice.readAloud"] }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/audio/synthesise/")).toBe(true));
    const spoken = (calls.find((call) => call.path === "/api/v1/audio/synthesise/")?.body as { text: string }).text;
    expect(spoken).toContain("Ceiling fan installation");
    expect(spoken).toContain("G-9");
    expect(spoken).toMatch(/5:00\s?pm/i);
    expect(spoken).not.toContain("House 5");
    expect(spoken).not.toContain("Ring twice");
    // A playback failure leaves the page usable.
    expect(await screen.findByText(en["voice.readAloudFailed"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["jobs.review.confirm"] })).toBeEnabled();
  });
});
