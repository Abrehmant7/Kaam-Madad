import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { en } from "../i18n/resources/en";
import { bootHandlers, errorEnvelope, jsonResponse, makeUser, mockApi } from "../test/http";
import { renderApp } from "../test/renderApp";

const TRANSCRIPT = "میں پنکھے لگاتا ہوں اور wiring ٹھیک کرتا ہوں، لیکن motor rewinding نہیں کرتا۔";

const CATALOG = {
  "GET /api/v1/catalog/trades/": jsonResponse({
    count: 1, next: null, previous: null,
    results: [{ code: "electrician", labels: { ur: "الیکٹریشن", en: "Electrician" }, icon: "zap", sort_order: 10, service_count: 2 }],
  }),
  "GET /api/v1/catalog/service-tags/": jsonResponse({
    count: 2, next: null, previous: null,
    results: [
      { code: "elec_fan_install", trade: "electrician", labels: { ur: "پنکھے کی تنصیب", en: "Ceiling fan installation" }, icon: "fan", sort_order: 10 },
      { code: "elec_wiring_repair", trade: "electrician", labels: { ur: "وائرنگ کی مرمت", en: "Wiring repair" }, icon: "cable", sort_order: 20 },
    ],
  }),
  "GET /api/v1/catalog/areas/": jsonResponse({ count: 0, next: null, previous: null, results: [] }),
};

function interpretation(overrides: Record<string, unknown> = {}) {
  const fields = { name: "احمد", trade: "electrician", years_experience: 5, services_offered: ["elec_fan_install", "elec_wiring_repair"], services_not_offered: [] };
  return {
    id: "int-1",
    kind: "worker_introduction",
    language: "mixed",
    source: { text: TRANSCRIPT, transcription_id: "tr-1" },
    draft: { fields, missing: [], uncertain: [], unmatched_mentions: [{ phrase: "motor rewinding", negated: true }], heard: {} },
    corrections: {},
    effective_fields: fields,
    confirmed: null,
    provider: "fixture",
    model: "fixture-rules-v1",
    simulated: true,
    reused: false,
    ...overrides,
  };
}

class FakeAudio {
  duration = 2;
  onloadedmetadata: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  preload = "";
  set src(_value: string) {
    setTimeout(() => this.onloadedmetadata?.(), 0);
  }
  play = vi.fn().mockResolvedValue(undefined);
  pause = vi.fn();
}

beforeEach(() => {
  vi.stubGlobal("Audio", FakeAudio);
  URL.createObjectURL = vi.fn(() => "blob:local-audio");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => vi.unstubAllGlobals());

const worker = () => bootHandlers(makeUser({ preferred_language: "en" }));

describe("voice test page", () => {
  it("typed text → correct → confirm; synthesis failure keeps the corrections and allows retry", async () => {
    let synthAttempts = 0;
    const calls = mockApi({
      ...worker(),
      ...CATALOG,
      "POST /api/v1/interpretations/": jsonResponse(interpretation({ source: { text: "typed", transcription_id: null } }), 201),
      "PATCH /api/v1/interpretations/int-1/": jsonResponse(interpretation({ corrections: { name: "Ahmed Khan" } })),
      "POST /api/v1/interpretations/int-1/confirm/": jsonResponse(
        interpretation({ confirmed: { fields: { ...interpretation().draft.fields, name: "Ahmed Khan" }, confirmed_at: "x" } }),
      ),
      "POST /api/v1/audio/synthesise/": () =>
        ++synthAttempts === 1
          ? jsonResponse(errorEnvelope("ai_provider_unavailable", "r1", { capability: "text_to_speech" }), 502)
          : jsonResponse({ id: "s1", language: "en", voice: "fixture-tone-en", provider: "fixture", simulated: true, mime_type: "audio/wav", size_bytes: 10, content_url: "/api/v1/audio/syntheses/s1/content/", reused: false }, 201),
      "GET /api/v1/audio/syntheses/s1/content/": new Response(new Blob(["RIFF"]), { status: 200, headers: { "Content-Type": "audio/wav" } }),
    });

    renderApp("/voice-test", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["voice.typeInstead"] }));
    await userEvent.type(screen.getByLabelText(en["voice.typeLabel"]), "I install fans");
    await userEvent.click(screen.getByRole("button", { name: en["voice.createDraft"] }));

    expect(await screen.findByText(en["voice.step3"])).toBeInTheDocument();
    expect(screen.getAllByText(en["voice.simulated"]).length).toBeGreaterThan(0);
    expect(screen.getByText("“motor rewinding”")).toBeInTheDocument();
    expect(screen.getByText(en["voice.mentionNegated"])).toBeInTheDocument();

    const name = screen.getByLabelText(en["voice.field.name"]);
    await userEvent.clear(name);
    await userEvent.type(name, "Ahmed Khan");
    await userEvent.click(screen.getByRole("button", { name: en["voice.confirm"] }));
    expect(await screen.findByText(en["voice.confirmedNotice"])).toBeInTheDocument();
    expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ fields: { name: "Ahmed Khan" } });

    // Synthesis fails: the confirmed text stays visible, a retry is offered.
    await userEvent.click(screen.getByRole("button", { name: en["voice.readAloud"] }));
    expect(await screen.findByText(en["voice.readAloudFailed"])).toBeInTheDocument();
    expect(screen.getByText(/Ahmed Khan/, { selector: "blockquote" })).toBeInTheDocument();
    expect(screen.getByLabelText(en["voice.field.name"])).toHaveValue("Ahmed Khan");

    await userEvent.click(screen.getByRole("button", { name: en["common.retry"] }));
    await waitFor(() => expect(screen.queryByText(en["voice.readAloudFailed"])).not.toBeInTheDocument());
    expect(synthAttempts).toBe(2);
  });

  it("upload → transcribe keeps the English term and negation; a failure keeps the recording and does not re-upload", async () => {
    let transcribeAttempts = 0;
    const calls = mockApi({
      ...worker(),
      ...CATALOG,
      "POST /api/v1/audio/clips/": jsonResponse({ id: "clip-1", purpose: "worker_introduction", source: "upload", mime_type: "audio/wav", size_bytes: 100, duration_seconds: 2, created_at: "x", content_url: "/api/v1/audio/clips/clip-1/content/" }, 201),
      "POST /api/v1/audio/transcribe/": () =>
        ++transcribeAttempts === 1
          ? jsonResponse(errorEnvelope("ai_provider_not_configured", "r2", { capability: "speech_to_text" }), 503)
          : jsonResponse({ id: "tr-1", clip_id: "clip-1", text: TRANSCRIPT, language: "mixed", language_hint: "en", no_speech: false, provider: "fixture", model: "fixture-stt-v1", simulated: true, reused: false }),
      "POST /api/v1/interpretations/": jsonResponse(interpretation(), 201),
    });

    renderApp("/voice-test", "en");
    // jsdom has no microphone: capability detection offers upload instead.
    expect(await screen.findByText(en["voice.recordingUnsupported"])).toBeInTheDocument();
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File([new Uint8Array(2048)], "note.wav", { type: "audio/wav" }));
    expect(await screen.findByText(en["voice.yourFile"])).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: en["voice.transcribe"] }));
    expect(await screen.findByText(en["errors.ai_provider_not_configured"])).toBeInTheDocument();
    expect(screen.getByText(en["voice.keptYourWork"])).toBeInTheDocument();
    expect(screen.getByText(en["voice.yourFile"])).toBeInTheDocument(); // recording kept

    await userEvent.click(screen.getByRole("button", { name: en["voice.transcribe"] }));
    expect(await screen.findByText(TRANSCRIPT)).toBeInTheDocument();
    expect(await screen.findByText(en["voice.step3"])).toBeInTheDocument();
    expect(calls.filter((call) => call.path === "/api/v1/audio/clips/")).toHaveLength(1); // not uploaded twice

    const upload = calls.find((call) => call.path === "/api/v1/audio/clips/")!;
    expect(upload.headers["X-CSRFToken"]).toBe("test-csrf-token");
    expect(upload.headers["Content-Type"]).toBeUndefined(); // multipart boundary set by the browser
  });

  it("rejects an oversized file before contacting the server", async () => {
    const calls = mockApi({ ...worker(), ...CATALOG });
    renderApp("/voice-test", "en");
    await screen.findByText(en["voice.recordingUnsupported"]);
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.wav", { type: "audio/wav" }));
    expect(await screen.findByText(en["voice.fileTooLarge"])).toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/v1/audio/clips/")).toBe(false);
  });

  it("explains a denied microphone and keeps upload available", async () => {
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("AudioContext", class {});
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error("denied"), { name: "NotAllowedError" })) },
    });
    mockApi({ ...worker(), ...CATALOG });
    renderApp("/voice-test", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["voice.record"].replace("{seconds}", "60") }));
    expect(await screen.findByText(en["voice.microphoneDenied"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["voice.upload"] })).toBeInTheDocument();
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
  });

  it("shows server validation errors on the right field when confirming", async () => {
    const base = interpretation();
    const fields = { ...base.draft.fields, name: null };
    const draft = { ...base, draft: { ...base.draft, fields, missing: ["name"] }, effective_fields: fields };
    mockApi({
      ...worker(),
      ...CATALOG,
      "POST /api/v1/interpretations/": jsonResponse(draft, 201),
      "POST /api/v1/interpretations/int-1/confirm/": jsonResponse(
        errorEnvelope("validation_error", "r3", undefined, { "fields.name": [{ code: "required", message: "required" }] }),
        400,
      ),
    });
    renderApp("/voice-test", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["voice.typeInstead"] }));
    await userEvent.type(screen.getByLabelText(en["voice.typeLabel"]), "text");
    await userEvent.click(screen.getByRole("button", { name: en["voice.createDraft"] }));
    expect(await screen.findByText(en["voice.missing"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["voice.confirm"] }));
    expect(await screen.findByText(en["fieldErrors.required"])).toBeInTheDocument();
    expect(screen.getByLabelText(en["voice.field.name"])).toHaveAttribute("aria-invalid", "true");
  });
});
