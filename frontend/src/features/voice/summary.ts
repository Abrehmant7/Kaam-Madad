import type { DraftFields, VoiceKind } from "../../api/voice";
import type { I18nContextValue } from "../../i18n/context";
import type { Language } from "../../i18n/types";
import type { CatalogData } from "./DraftEditor";

/** Plain-language summary of CONFIRMED fields, used for display and read-aloud. */
export function summaryText(
  kind: VoiceKind,
  fields: DraftFields,
  catalog: CatalogData,
  t: I18nContextValue["t"],
  language: Language,
): string {
  const label = (list: { code: string; labels: { ur: string; en: string } }[], code: string | null | undefined) =>
    list.find((item) => item.code === code)?.labels[language] ?? "";
  const services = (codes: string[] | undefined) =>
    (codes ?? []).map((code) => label(catalog.services, code)).filter(Boolean).join(language === "ur" ? "، " : ", ");
  const stop = language === "ur" ? "۔" : ".";
  const parts: string[] = [];
  const add = (key: Parameters<typeof t>[0], value: string | number | null | undefined) => {
    if (value !== null && value !== undefined && value !== "") parts.push(`${t(key)}: ${value}${stop}`);
  };

  add("voice.field.trade", label(catalog.trades, fields.trade));
  if (kind === "worker_introduction") {
    add("voice.field.name", fields.name);
    add("voice.field.years_experience", fields.years_experience ?? null);
    add("voice.field.services_offered", services(fields.services_offered));
    add("voice.field.services_not_offered", services(fields.services_not_offered));
  } else {
    add("voice.field.description", fields.description);
    add("voice.field.services", services(fields.services));
    add("voice.field.services_excluded", services(fields.services_excluded));
    add("voice.field.area", label(catalog.areas, fields.area));
    add("voice.field.preferred_time_text", fields.preferred_time_text);
    add("voice.field.budget_pkr", fields.budget_pkr ?? null);
  }
  return parts.join(" ");
}
