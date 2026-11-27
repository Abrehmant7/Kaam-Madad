import { describe, expect, it } from "vitest";

import type { Quote } from "../../api/conversations";
import { interpolate } from "../../i18n/context";
import { en } from "../../i18n/resources/en";
import { ur } from "../../i18n/resources/ur";
import { quoteSpeech } from "./quoteText";

const quote = {
  id: "q", version: 2, status: "submitted", timezone: "Asia/Karachi", inspection_only: false, scope: "Install two ceiling fans.",
  quantity: 2, labour_amount: "600.00", labour_basis: "per_item", materials: "worker_extra", materials_amount: null, visit_fee: null,
  visit_fee_treatment: "none", exclusions: "", start_at: "2030-01-10T12:00:00Z", end_at: "2030-01-10T14:00:00Z",
  totals: { labour_total: "1200.00", materials_total: null, visit_total: null, known_total: "1200.00", unknown: ["materials"], complete: false },
  submitted_at: null, superseded_at: null, expires_at: null, expired: false,
  check: { status: "passed", provider: "fixture", simulated: true, checked_at: null, failure: null }, manual_review_at: null, findings: [], issues: {},
} as Quote;
const tFor = (resources: Record<string, string>) => ((key: string, params?: Record<string, string | number>) => interpolate(resources[key] ?? key, params)) as never;

describe("quote read-aloud text", () => {
  it("speaks amounts as rupees without swallowing the full stop, and says unknown amounts are unknown", () => {
    const text = quoteSpeech(quote, "en", tFor(en));
    expect(text).toContain("600 rupees per item × 2 = 1,200 rupees.");
    expect(text).toContain("Install two ceiling fans.");
    expect(text).not.toContain("fans..");
    expect(text).toContain(`${en["quote.materials.worker_extra"]}: ${en["quote.unknown"]}.`);
    expect(text).toContain(`1,200 rupees ${en["quote.plusUnknown"]}.`);
    expect(text).not.toMatch(/PKR|\d\. rupees/);
  });

  it("uses the Urdu full stop and Urdu currency word", () => {
    const text = quoteSpeech(quote, "ur", tFor(ur));
    expect(text).toContain("1,200 روپے۔");
    expect(text).not.toMatch(/PKR|\d\.\s/);
  });
});
