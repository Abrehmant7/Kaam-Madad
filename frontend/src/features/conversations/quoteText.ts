import type { Quote, QuoteTerms } from "../../api/conversations";
import type { I18nContextValue } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import { isolateLtr } from "../jobs/text";
import { formatDate, formatTime } from "../jobs/time";

type T = I18nContextValue["t"];

export const money = (value: string | null | undefined) =>
  value == null ? null : `PKR ${Number(value).toLocaleString("en-PK", { maximumFractionDigits: 2 })}`;

/** "PKR 600 per item × 2 = PKR 1,200" / "PKR 1,500 for the whole job" / "Unknown". */
export function labourText(quote: QuoteTerms & { totals?: Quote["totals"] }, t: T): string {
  if (quote.labour_amount == null) return quote.inspection_only ? t("quote.repairUnknown") : t("quote.unknown");
  if (quote.labour_basis === "per_item") {
    return t("quote.labourPerItem", { amount: money(quote.labour_amount) ?? "", quantity: quote.quantity ?? 1, total: money(quote.totals?.labour_total) ?? "" });
  }
  return t("quote.labourTotal", { amount: money(quote.labour_amount) ?? "" });
}

export function materialsText(quote: QuoteTerms, t: T): string {
  if (!quote.materials) return t("quote.unknown");
  const base = t(`quote.materials.${quote.materials}`);
  if (quote.materials !== "worker_extra") return base;
  return `${base}: ${quote.materials_amount == null ? t("quote.unknown") : money(quote.materials_amount)}`;
}

export function visitText(quote: QuoteTerms, t: T): string {
  const base = t(`quote.visit.${quote.visit_fee_treatment}`);
  return quote.visit_fee && quote.visit_fee_treatment !== "none" && quote.visit_fee_treatment !== "included" ? `${base}: ${money(quote.visit_fee)}` : base;
}

export function windowText(quote: QuoteTerms, language: Language): { date: string; time: string } | null {
  if (!quote.start_at || !quote.end_at) return null;
  return { date: formatDate(quote.start_at, language), time: `${formatTime(quote.start_at, language)} – ${formatTime(quote.end_at, language)}` };
}

/** Read-aloud of the key terms (work, price, materials, visit fee, exclusions, time, total). */
export function quoteSpeech(quote: Quote, language: Language, t: T): string {
  const when = windowText(quote, language);
  const stop = language === "ur" ? "۔" : "."; // Urdu full stop
  const line = (label: string, value: string) => `${label}: ${value.trim().replace(/[.۔]$/, "")}${stop}`;
  const parts = [
    t("quote.speech.version", { version: quote.version ?? "" }),
    line(t("quote.field.scope"), quote.scope),
    line(t("quote.field.labour"), labourText(quote, t)),
    line(t("quote.field.materials"), materialsText(quote, t)),
    line(t("quote.field.visit"), visitText(quote, t)),
  ];
  if (quote.exclusions) parts.push(line(t("quote.field.exclusions"), quote.exclusions));
  if (when) parts.push(line(t("quote.field.when"), `${when.date}${language === "ur" ? "، " : ", "}${isolateLtr(when.time)}`));
  if (quote.totals) {
    parts.push(line(t("quote.field.total"), `${money(quote.totals.known_total)}${quote.totals.complete ? "" : ` ${t("quote.plusUnknown")}`}`));
  }
  // Spoken amounts: "1,500 روپے" / "1,500 rupees" rather than the written "PKR 1,500".
  // The number pattern stops before a sentence's full stop ("PKR 1,200." → "1,200 rupees.").
  return parts.join(" ").replace(/PKR (\d[\d,]*(?:\.\d+)?)/g, language === "ur" ? "$1 روپے" : "$1 rupees");
}
