import { describe, expect, it } from "vitest";

import type { SharedSummary } from "../../api/invitations";
import { en } from "../../i18n/resources/en";
import { ur } from "../../i18n/resources/ur";
import type { TranslationKey, TranslationParams } from "../../i18n/types";
import { AREAS, SERVICES, TRADES } from "../../test/http";
import type { JobCatalog } from "../jobs/catalog";
import { sharedSpeech, spokenDescription } from "./SharedJob";

const catalog = { trades: TRADES, services: SERVICES, areas: AREAS } as unknown as JobCatalog;
const translate = (resources: Record<string, string>) => (key: TranslationKey, params: TranslationParams = {}) =>
  Object.entries(params).reduce((text, [name, value]) => text.replace(`{${name}}`, String(value)), resources[key] ?? key);

const URDU_ORIGINAL = "دو چھت کے پنکھے لگانے ہیں، اے سی کی سروس نہیں چاہیے۔";
const ENGLISH = "Please install two ceiling fans. No AC service.";
const job = (extra: Partial<SharedSummary>): SharedSummary => ({
  description: URDU_ORIGINAL, description_language: "ur", description_ur: null, trade: "electrician", services: ["elec_fan_install"],
  services_excluded: [], city: "islamabad", area: "isb-g-9", window_start: "2030-01-10T12:00:00Z", window_end: "2030-01-10T14:00:00Z",
  budget_preference_pkr: null, has_photos: false, ...extra,
});

describe("SharedJob read-aloud (regression)", () => {
  it("reads the original description in Urdu playback when it is already in Urdu and there is no approved translation", () => {
    const spoken = sharedSpeech(job({}), catalog, "ur", translate(ur));
    expect(spoken).toContain(URDU_ORIGINAL);
    expect(spoken).toContain("چھت کے پنکھے کی تنصیب"); // structured details are still read
    expect(spoken).toContain("جی-9");
  });

  it("prefers the customer-approved Urdu version over the original", () => {
    const approved = "جی-9 میں دو پنکھے لگانے ہیں۔";
    const spoken = sharedSpeech(job({ description: ENGLISH, description_language: "en", description_ur: approved }), catalog, "ur", translate(ur));
    expect(spoken).toContain(approved);
    expect(spoken).not.toContain(ENGLISH);
  });

  it("keeps the structured fallback for an untranslated English request read in Urdu", () => {
    const spoken = sharedSpeech(job({ description: ENGLISH, description_language: "en" }), catalog, "ur", translate(ur));
    expect(spoken).not.toContain(ENGLISH);
    expect(spoken).not.toContain(ur["jobs.speech.description"].replace("{text}", ""));
    expect(spoken).toContain("چھت کے پنکھے کی تنصیب");
  });

  it("judges older invitations without a language by script, and reads English notes to English readers only", () => {
    expect(spokenDescription(job({ description_language: undefined }), "ur")).toBe(URDU_ORIGINAL);
    expect(spokenDescription(job({ description: ENGLISH, description_language: undefined }), "ur")).toBeNull();
    expect(spokenDescription(job({ description: ENGLISH, description_language: "en" }), "en")).toBe(ENGLISH);
    expect(spokenDescription(job({}), "en")).toBeNull(); // Urdu notes are not read in the English voice
    expect(sharedSpeech(job({ description: ENGLISH, description_language: "en" }), catalog, "en", translate(en))).toContain(ENGLISH);
  });
});
