import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/resources/en";
import { ur } from "../i18n/resources/ur";
import { AREAS, bootHandlers, DEMO_CONFIG, errorEnvelope, jsonResponse, makeDashboard, makeUser, mockApi, SERVICES, TRADES, workerHandlers } from "../test/http";
import { renderApp } from "../test/renderApp";

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const worker = (language: "en" | "ur" = "en") => makeUser({ preferred_language: language });
const customer = () => makeUser({ role: "customer", preferred_language: "en" });
const ENGLISH = "Please install two ceiling fans in G-9 tomorrow evening. No AC service needed.";
const URDU = "چھت کے پنکھے لگانے ہیں۔ اے سی کی سروس نہیں چاہیے۔";

const clip = (purpose: string) =>
  jsonResponse({ id: "clip-1", purpose, source: "upload", mime_type: "audio/wav", size_bytes: 100, duration_seconds: 2, created_at: "x", content_url: "/api/v1/audio/clips/clip-1/content/" }, 201);
const transcript = (text: string) =>
  jsonResponse({ id: "tr-1", clip_id: "clip-1", text, language: "mixed", language_hint: "en", no_speech: false, provider: "elevenlabs", model: "scribe_v3", simulated: false, reused: false });
const interpretation = (kind: string, fields: Record<string, unknown>, draft: Record<string, unknown> = {}) =>
  jsonResponse({
    id: "int-1", kind, language: "mixed", source: { text: "x", transcription_id: "tr-1" },
    draft: { fields, missing: [], uncertain: [], unmatched_mentions: [], heard: {}, ...draft },
    corrections: {}, effective_fields: fields, confirmed: null, provider: "groq", model: "openai/gpt-oss-120b", simulated: false, reused: false,
  }, 201);

async function uploadVoice() {
  const summary = screen.getByText(en["voiceAnswer.open"]);
  await userEvent.click(summary);
  const input = summary.closest("details")!.querySelector<HTMLInputElement>('input[type="file"]')!;
  await userEvent.upload(input, new File([new Uint8Array(2048)], "answer.wav", { type: "audio/wav" }));
  expect(await screen.findByText(en["voice.yourFile"], {}, { timeout: 5000 })).toBeInTheDocument();
  const fill = screen.getByRole("button", { name: en["voiceAnswer.fill"] });
  await waitFor(() => expect(fill).toBeEnabled());
  await userEvent.click(fill);
}

describe("worker signup: answer by voice", () => {
  it("fills screen 2 from the voice answer, leaving everything editable and unsaved", { timeout: 20000 }, async () => {
    const calls = mockApi({
      ...bootHandlers(worker()),
      ...workerHandlers(makeDashboard("work")),
      "POST /api/v1/audio/clips/": clip("onboarding_work"),
      "POST /api/v1/audio/transcribe/": transcript("میں الیکٹریشن ہوں۔ پنکھے لگاتا ہوں اور wiring۔ UPS نہیں کرتا۔"),
      "POST /api/v1/interpretations/": interpretation("onboarding_work", {
        trade: "electrician", services_offered: ["elec_fan_install", "elec_wiring_repair"], primary_specialities: [],
        services_not_offered: ["elec_ups_inverter"],
      }, { uncertain: ["primary_specialities"] }),
    });
    renderApp("/worker/setup/work", "en");
    await screen.findByRole("heading", { level: 1, name: en["onboarding.work.title"] });
    await uploadVoice();
    expect(await screen.findByText(en["voiceAnswer.applied"])).toBeInTheDocument();
    expect(screen.getByText(en["voiceAnswer.unclear"])).toBeInTheDocument();
    const offered = await screen.findByRole("group", { name: en["onboarding.work.servicesLabel"] });
    await waitFor(() => expect(within(offered).getByRole("button", { name: /Ceiling fan installation/ })).toHaveAttribute("aria-pressed", "true"));
    expect(within(offered).getByRole("button", { name: /Wiring repair/ })).toHaveAttribute("aria-pressed", "true");
    // The unclear main speciality is left for the worker to choose.
    const main = screen.getByRole("radiogroup", { name: en["onboarding.work.mainLabel"] });
    expect(within(main).getAllByRole("radio").every((radio) => radio.getAttribute("aria-checked") !== "true")).toBe(true);
    expect(calls.find((call) => call.path === "/api/v1/interpretations/")?.body).toMatchObject({ kind: "onboarding_work", transcription_id: "tr-1" });
    expect(calls.some((call) => call.method === "PUT")).toBe(false); // nothing saved until the worker saves
  });

  it("keeps manual selection usable when speech-to-text fails", { timeout: 20000 }, async () => {
    mockApi({
      ...bootHandlers(worker()),
      ...workerHandlers(makeDashboard("work")),
      "POST /api/v1/audio/clips/": clip("onboarding_work"),
      "POST /api/v1/audio/transcribe/": jsonResponse(errorEnvelope("ai_provider_limit_reached", "r1", { capability: "speech_to_text" }), 429),
    });
    renderApp("/worker/setup/work", "en");
    await screen.findByRole("heading", { level: 1, name: en["onboarding.work.title"] });
    await uploadVoice();
    expect(await screen.findByText(en["voiceAnswer.failed"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Electrician/ }));
    const offered = await screen.findByRole("group", { name: en["onboarding.work.servicesLabel"] });
    await userEvent.click(within(offered).getByRole("button", { name: /Ceiling fan installation/ }));
    expect(within(offered).getByRole("button", { name: /Ceiling fan installation/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("fills screen 3 from voice, lists refused areas, and reads the worker's choices aloud without private data", { timeout: 20000 }, async () => {
    const calls = mockApi({
      ...bootHandlers(worker()),
      ...workerHandlers(makeDashboard("areas")),
      "POST /api/v1/audio/clips/": clip("onboarding_areas"),
      "POST /api/v1/audio/transcribe/": transcript("اسلام آباد میں G-9 اور G-10۔ صدر نہیں جاتا۔"),
      "POST /api/v1/interpretations/": interpretation("onboarding_areas", { city: "islamabad", service_areas: ["isb-g-9", "isb-g-10"] },
        { not_selected: ["rwp-saddar"] }),
      "POST /api/v1/audio/synthesise/": jsonResponse(errorEnvelope("ai_provider_not_configured", "r2", { capability: "text_to_speech" }), 503),
    });
    renderApp("/worker/setup/areas", "en");
    await screen.findByRole("heading", { level: 1, name: en["onboarding.areas.title"] });
    await uploadVoice();
    expect(await screen.findByText(en["voiceAnswer.notGoing"].replace("{areas}", "Saddar"))).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /G-10/ })).toHaveAttribute("aria-pressed", "true"));

    const listen = screen.getByRole("region", { name: en["onboarding.listen.heading"] });
    await userEvent.click(within(listen).getByRole("button", { name: en["voice.readAloud"] }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/audio/synthesise/")).toBe(true));
    const spoken = (calls.find((call) => call.path === "/api/v1/audio/synthesise/")?.body as { text: string; language: string });
    expect(spoken.language).toBe("en");
    expect(spoken.text).toBe(
      "Trade: Electrician. Work I do: Ceiling fan installation, Wiring repair. Main speciality: Ceiling fan installation. " +
        "Areas: G-9, G-10, Islamabad.",
    );
    for (const secret of ["4567", "+92", "password", "CNIC"]) expect(spoken.text).not.toContain(secret);
  });
});

describe("demo verification", () => {
  const sample = () => new Response(new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], { type: "image/png" }));

  it("uses the two sample images and shows Demo verification complete", async () => {
    const calls = mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/identity/cases/": jsonResponse({ case: null, provider: { provider: "demo_registry", available: true, simulated: true } }),
      "GET /demo-samples/sample-cnic.png": sample,
      "GET /demo-samples/sample-selfie.png": sample,
      "POST /api/v1/identity/demo-verification/": jsonResponse({
        case: { id: "case-1", status: "demo_approved", method: "demo_sample_upload", simulated: true, counts_here: true },
        eligibility: { can_take_jobs: true, receives_requests: true, reasons: [] },
      }),
    });
    renderApp("/worker/verify", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["demoVerify.title"] })).toBeInTheDocument();
    expect(screen.getAllByText(en["demoVerify.sampleOnly"]).length).toBeGreaterThan(0);
    expect(screen.getByText(en["demoVerify.notNadra"])).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: en["demoVerify.submit"] });
    expect(submit).toBeDisabled();
    for (const slot of [en["demoVerify.cnic"], en["demoVerify.selfie"]]) {
      await userEvent.click(within(screen.getByRole("region", { name: slot })).getByRole("button", { name: en["demoVerify.useSample"] }));
    }
    await waitFor(() => expect(submit).toBeEnabled());
    await userEvent.click(submit);
    expect(await screen.findByText(en["demoVerify.complete"])).toBeInTheDocument();
    const posted = calls.find((call) => call.path === "/api/v1/identity/demo-verification/")!;
    const form = posted.body as FormData;
    expect([...form.keys()]).toEqual(["cnic_image", "selfie_image"]);
  });

  it("explains that demo verification is unavailable in a live deployment", async () => {
    mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/config/": jsonResponse({ ...DEMO_CONFIG, deployment_mode: "live" }),
      "GET /api/v1/identity/cases/": jsonResponse({ case: null, provider: { provider: "unconfigured", available: false, simulated: false } }),
    });
    renderApp("/worker/verify", "en");
    expect(await screen.findByText(en["demoVerify.unavailable"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["demoVerify.submit"] })).not.toBeInTheDocument();
  });
});

describe("English request, Urdu worker", () => {
  const catalog = {
    "GET /api/v1/catalog/trades/": jsonResponse(page(TRADES)),
    "GET /api/v1/catalog/service-tags/": jsonResponse(page(SERVICES)),
    "GET /api/v1/catalog/areas/": jsonResponse(page(AREAS)),
  };
  const shared = (extra: Record<string, unknown>) => ({
    id: "inv-1", status: "active", created_at: "x", seen_at: "x", closed_at: null, decline_reason: null, booking: null,
    job: {
      description: ENGLISH, description_language: "en", description_ur: null, trade: "electrician", services: ["elec_fan_install"],
      services_excluded: [], city: "islamabad", area: "isb-g-9", window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z",
      budget_preference_pkr: null, has_photos: false, ...extra,
    },
  });

  it("shows the approved Urdu description first and reads it aloud with the work, area and time", async () => {
    const calls = mockApi({
      ...bootHandlers(worker("ur")), ...catalog,
      "GET /api/v1/invitations/inv-1/": jsonResponse(shared({ description_ur: URDU })),
      "POST /api/v1/audio/synthesise/": jsonResponse(errorEnvelope("ai_provider_not_configured", "r3", { capability: "text_to_speech" }), 503),
    });
    renderApp("/worker/invitations/inv-1", "ur");
    expect(await screen.findByText(ur["jobs.summary.descriptionUr"])).toBeInTheDocument();
    expect(screen.getAllByText(URDU).length).toBeGreaterThan(0);
    expect(screen.getByText(ur["jobs.summary.originalWords"].replace("{language}", ur["jobs.language.en"]))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: ur["voice.readAloud"] }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/audio/synthesise/")).toBe(true));
    const spoken = (calls.find((call) => call.path === "/api/v1/audio/synthesise/")?.body as { text: string }).text;
    expect(spoken).toContain(URDU);
    expect(spoken).toContain("چھت کے پنکھے کی تنصیب");
    expect(spoken).toContain("جی-9");
    expect(spoken).not.toContain(ENGLISH);
  });

  it("without an approved Urdu version shows the original notes marked as English and still reads the details", async () => {
    const calls = mockApi({
      ...bootHandlers(worker("ur")), ...catalog,
      "GET /api/v1/invitations/inv-1/": jsonResponse(shared({})),
      "POST /api/v1/audio/synthesise/": jsonResponse(errorEnvelope("ai_provider_not_configured", "r3", { capability: "text_to_speech" }), 503),
    });
    renderApp("/worker/invitations/inv-1", "ur");
    expect(await screen.findByText(ur["jobs.summary.originalWords"].replace("{language}", ur["jobs.language.en"]))).toBeInTheDocument();
    expect(screen.queryByText(ur["jobs.summary.descriptionUr"])).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: ur["voice.readAloud"] }));
    await waitFor(() => expect(calls.some((call) => call.path === "/api/v1/audio/synthesise/")).toBe(true));
    const spoken = (calls.find((call) => call.path === "/api/v1/audio/synthesise/")?.body as { text: string }).text;
    expect(spoken).toContain("چھت کے پنکھے کی تنصیب");
    expect(spoken).not.toContain("Please install");
  });

  it("lets the customer review, edit and approve the Urdu wording; editing the description withdraws the approval", async () => {
    const job = {
      id: "job-1", status: "draft", created_at: "x", updated_at: "x", confirmed_at: null,
      source: { kind: "text", language: "en", original_text: ENGLISH, audio_clip_id: null, transcription_id: null },
      details: {
        description: ENGLISH, trade: "electrician", services: ["elec_fan_install"], services_excluded: [], city: "islamabad", area: "isb-g-9",
        preferred_time_text: "tomorrow evening", window_start: null, window_end: null, timezone: "Asia/Karachi", address_private: "",
        access_notes: "", budget_pkr: null,
      },
      suggestions: { interpretation_id: "i1", provider: "groq", simulated: false, fields: {}, missing: [], uncertain: [], unmatched_mentions: [], heard: {} },
      urdu: { needed: true, text: URDU, status: "suggested", description_language: "en" },
      photos: [], issues: {}, ready_to_confirm: false, booking: null,
    };
    const calls = mockApi({
      ...bootHandlers(customer()), ...catalog,
      "GET /api/v1/jobs/job-1/": jsonResponse(job),
      "PATCH /api/v1/jobs/job-1/": jsonResponse({ ...job, urdu: { ...job.urdu, status: "approved" } }),
    });
    renderApp("/customer/requests/job-1/details", "en");
    expect(await screen.findByText(en["jobs.urdu.heading"])).toBeInTheDocument();
    expect(screen.getByText(en["jobs.urdu.status.suggested"])).toBeInTheDocument();
    expect(screen.getByLabelText(en["jobs.field.description"])).toHaveValue(ENGLISH); // the original is kept
    const urdu = screen.getByLabelText(en["jobs.urdu.label"]);
    expect(urdu).toHaveValue(URDU);
    const approve = screen.getByRole("checkbox", { name: en["jobs.urdu.approve"] });
    await userEvent.click(approve);
    expect(approve).toBeChecked();
    // Changing the customer's own description means the Urdu wording must be checked again.
    await userEvent.type(screen.getByLabelText(en["jobs.field.description"]), " Three fans.");
    expect(approve).not.toBeChecked();
    await userEvent.click(approve);
    await userEvent.type(urdu, " تین پنکھے۔");
    await userEvent.click(approve);
    await userEvent.click(screen.getByRole("button", { name: en["jobs.details.saveDraft"] }));
    await waitFor(() => expect(calls.some((call) => call.method === "PATCH")).toBe(true));
    expect(calls.find((call) => call.method === "PATCH")?.body).toMatchObject({
      description: `${ENGLISH} Three fans.`, description_ur: `${URDU} تین پنکھے۔`, description_ur_approved: true,
    });
  });
});
