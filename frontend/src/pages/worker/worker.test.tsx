import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../../i18n/resources/en";
import { bootHandlers, errorEnvelope, jsonResponse, makeDashboard, makeUser, mockApi, workerHandlers } from "../../test/http";
import { renderApp } from "../../test/renderApp";

const worker = () => makeUser({ preferred_language: "en" });
const tile = (name: string) => screen.getByRole("button", { name: new RegExp(name) });
const radio = (group: string, name: string) => within(screen.getByRole("radiogroup", { name: group })).getByRole("radio", { name: new RegExp(name) });

function baseCase(overrides: Record<string, unknown> = {}) {
  return {
    id: "case-1", status: "in_progress", case_id: "case-1", method: null, masked_cnic: null, simulated: false,
    counts_here: false, decided_at: null, updated_at: "2026-11-27T10:00:00Z",
    consent: { given_at: "2026-11-27T10:00:00Z", version: "2026-11-27" },
    scan: { count: 0, scanned_at: null, width: null, height: null },
    ocr: { status: "not_run", provider: null, engine: null, rotation: 0, failure: null, simulated: false, name: null, cnic_number: null },
    review: { submitted_at: null, name_corrected: false, number_corrected: false },
    registry: { outcome: "not_checked", provider: null, simulated: false, reference: null, checked_at: null, attempts: 0, demo_address: null },
    ...overrides,
  };
}
const scanned = (name: string | null, number: string | null, status = "read") =>
  baseCase({ scan: { count: 1, scanned_at: "x", width: 856, height: 546 }, ocr: { ...baseCase().ocr, status, provider: "tesseract", engine: "tesseract v5.4.0", name, cnic_number: number } });

describe("worker onboarding (screens 2 and 3)", () => {
  it("resumes at the unfinished step after a refresh or a new login", async () => {
    mockApi({ ...bootHandlers(worker()), ...workerHandlers(makeDashboard("areas")) });
    const { router } = renderApp("/worker", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["onboarding.areas.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker/setup/areas");
  });

  it("does not open screen 3 before screen 2 is complete", async () => {
    mockApi({ ...bootHandlers(worker()), ...workerHandlers(makeDashboard("work")) });
    const { router } = renderApp("/worker/setup/areas", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["onboarding.work.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker/setup/work");
  });

  it("chooses work and areas with tiles, shows server validation, and opens the dashboard", async () => {
    let workAttempts = 0;
    let saved = makeDashboard("work"); // what the server has stored so far
    const calls = mockApi({
      ...bootHandlers(worker()),
      ...workerHandlers(),
      "GET /api/v1/workers/me/": () => jsonResponse(saved),
      "PUT /api/v1/workers/me/work/": () => {
        if (++workAttempts === 1) {
          return jsonResponse(errorEnvelope("validation_error", "r1", undefined, { primary_specialities: [{ code: "primary_not_offered", message: "x" }] }), 400);
        }
        saved = makeDashboard("areas");
        return jsonResponse(saved);
      },
      "PUT /api/v1/workers/me/areas/": () => {
        saved = makeDashboard(null);
        return jsonResponse(saved);
      },
    });
    const { router } = renderApp("/worker/setup/work", "en");
    expect(await screen.findByText(en["instructions.onboarding_work"])).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("radio", { name: /Electrician/ }));
    const offered = await screen.findByRole("group", { name: en["onboarding.work.servicesLabel"] });
    await userEvent.click(within(offered).getByRole("button", { name: /Ceiling fan installation/ }));
    await userEvent.click(within(offered).getByRole("button", { name: /Wiring repair/ }));
    await userEvent.click(radio(en["onboarding.work.mainLabel"], "Ceiling fan installation"));
    await userEvent.click(screen.getByText(en["onboarding.work.moreOptions"]));
    await userEvent.click(within(screen.getByRole("group", { name: en["onboarding.work.excludedLabel"] })).getByRole("button", { name: /UPS/ }));
    await userEvent.click(screen.getByRole("button", { name: en["onboarding.work.save"] }));
    expect(await screen.findByText(en["fieldErrors.primary_not_offered"])).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: en["onboarding.work.save"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["onboarding.areas.title"] })).toBeInTheDocument();
    expect(calls.filter((call) => call.method === "PUT")[0]?.body).toEqual({
      trade: "electrician",
      services_offered: ["elec_fan_install", "elec_wiring_repair"],
      primary_specialities: ["elec_fan_install"],
      services_not_offered: ["elec_ups_inverter"],
    });

    // Screen 3: manual choice of city and areas; no location permission is requested.
    expect(screen.getByText(en["onboarding.areas.explain"])).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("radio", { name: /Islamabad/ }));
    expect(screen.queryByRole("button", { name: /Saddar/ })).not.toBeInTheDocument(); // other city's areas hidden
    await userEvent.click(tile("G-9"));
    await userEvent.click(screen.getByRole("button", { name: en["onboarding.areas.save"] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/worker"));
    expect(calls.find((call) => call.path === "/api/v1/workers/me/areas/")?.body).toEqual({ city: "islamabad", service_areas: ["isb-g-9"] });
    expect(await screen.findByRole("heading", { level: 1, name: en["worker.dashboard.title"] })).toBeInTheDocument();
  }, 20000);
});

describe("worker dashboard", () => {
  it("is usable without verification and explains why jobs are blocked", async () => {
    mockApi({ ...bootHandlers(worker()), ...workerHandlers(makeDashboard(null)) });
    renderApp("/worker", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["worker.dashboard.title"] })).toBeInTheDocument();
    expect(screen.getByText(en["worker.eligibility.no"])).toBeInTheDocument();
    expect(screen.getByText(en["worker.eligibility.reason.identity_not_started"])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["worker.identity.cta"] })).toHaveAttribute("href", "/worker/verify");
    expect(screen.getByText(en["worker.profile.complete"])).toBeInTheDocument();
    expect(screen.getByText("Ceiling fan installation")).toBeInTheDocument(); // main speciality label
    expect(screen.getByRole("link", { name: en["worker.profile.editWork"] })).toHaveAttribute("href", "/worker/setup/work");
    expect(screen.getByRole("link", { name: en["home.managePhone"] })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["worker.voiceIntro"] })).toBeInTheDocument();
  });
});

describe("identity verification", () => {
  it("scans, lets the worker correct the OCR fields, and shows the demo approval", async () => {
    const calls = mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/identity/cases/": jsonResponse({ case: null, provider: { provider: "demo_registry", available: true, simulated: true } }),
      "POST /api/v1/identity/cases/": jsonResponse({ case: baseCase(), provider: { provider: "demo_registry", available: true, simulated: true } }, 201),
      "POST /api/v1/identity/cases/case-1/scan/": jsonResponse({ case: scanned("Bilal Ahmd", "00000-1234567-1") }),
      "POST /api/v1/identity/cases/case-1/submit/": jsonResponse({
        case: baseCase({
          status: "demo_approved", method: "demo_registry", masked_cnic: "*****-*****67-1", counts_here: true,
          registry: { outcome: "match", provider: "demo_registry", simulated: true, reference: "DEMO-REG-0001", checked_at: "x", attempts: 1, demo_address: "House 12, Street 4, Demo Town, Islamabad" },
        }),
        eligibility: { can_take_jobs: true, receives_requests: true, reasons: [] },
      }),
    });
    renderApp("/worker/verify", "en");
    expect(await screen.findByText(en["verify.why.heading"])).toBeInTheDocument();
    const agree = screen.getByRole("button", { name: en["verify.start"] });
    expect(agree).toBeDisabled();
    await userEvent.click(screen.getByLabelText(en["verify.consent"]));
    await userEvent.click(agree);

    const file = new File([new Uint8Array(2048)], "card.png", { type: "image/png" });
    fireEvent.change(await screen.findByTestId("upload-input"), { target: { files: [file] } });
    expect(await screen.findByText(en["verify.ocr.read"])).toBeInTheDocument();
    const nameField = screen.getByLabelText(en["verify.name.label"]);
    expect(nameField).toHaveValue("Bilal Ahmd");
    expect(screen.getByLabelText(en["verify.number.label"], { exact: false })).toHaveValue("00000-1234567-1");
    expect(screen.queryByText(en["verify.edited"])).not.toBeInTheDocument();
    await userEvent.clear(nameField);
    await userEvent.type(nameField, "Bilal Ahmed");
    expect(screen.getByText(en["verify.edited"])).toBeInTheDocument(); // correction shown apart from the scan
    expect(screen.getByText("Bilal Ahmd")).toBeInTheDocument(); // the original OCR value stays visible

    await userEvent.click(screen.getByRole("button", { name: en["verify.submit"] }));
    expect(await screen.findByText(en["verify.result.passed"])).toBeInTheDocument();
    expect(screen.getByText(en["verify.demoAddress"])).toBeInTheDocument();
    expect(screen.getByText("House 12, Street 4, Demo Town, Islamabad")).toBeInTheDocument();
    expect(screen.getByText("*****-*****67-1")).toBeInTheDocument();
    expect(calls.find((call) => call.path.endsWith("/submit/"))?.body).toEqual({ name: "Bilal Ahmed", cnic_number: "00000-1234567-1" });
    expect(calls.find((call) => call.path.endsWith("/scan/"))?.body).toBeInstanceOf(FormData);
  }, 20000);

  it("shows a name mismatch and keeps the fields for a retry", async () => {
    mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/identity/cases/": jsonResponse({
        case: { ...scanned("Kamran Shah", "00000-1234567-1"), status: "no_match", registry: { ...baseCase().registry, outcome: "name_mismatch", attempts: 1, provider: "demo_registry", simulated: true } },
        provider: { provider: "demo_registry", available: true, simulated: true },
      }),
    });
    renderApp("/worker/verify", "en");
    expect(await screen.findByText(en["verify.result.nameMismatch"])).toBeInTheDocument();
    expect(screen.getByLabelText(en["verify.name.label"])).toHaveValue("Kamran Shah");
    expect(screen.getByRole("button", { name: en["verify.submit"] })).toBeEnabled();
  });

  it("explains a missing Tesseract installation as a setup error", async () => {
    mockApi({
      ...bootHandlers(worker()),
      "GET /api/v1/identity/cases/": jsonResponse({ case: baseCase(), provider: { provider: "demo_registry", available: true, simulated: true } }),
      "POST /api/v1/identity/cases/case-1/scan/": jsonResponse(
        errorEnvelope("ai_provider_not_configured", "r9", { capability: "cnic_ocr", reason: "tesseract_not_found", case: { ...baseCase(), scan: { count: 1, scanned_at: "x", width: 856, height: 546 }, ocr: { ...baseCase().ocr, status: "failed", failure: "tesseract_not_found" } } }),
        503,
      ),
    });
    renderApp("/worker/verify", "en");
    fireEvent.change(await screen.findByTestId("upload-input"), { target: { files: [new File([new Uint8Array(2048)], "card.jpg", { type: "image/jpeg" })] } });
    expect(await screen.findByText(en["verify.ocr.setup"])).toBeInTheDocument();
    expect(screen.queryByLabelText(en["verify.name.label"])).not.toBeInTheDocument(); // no typing-only approval path
  });
});
